import numpy as np
import scipy as sp
from scipy.spatial.distance import pdist
from numba import jit


def partition_tree(X, metric="correlation"):
    X_full_rank = X + np.random.randn(*X.shape) * 1e-8
    D = sp.spatial.distance.pdist(X_full_rank.fillna(X_full_rank.mean()).T, metric=metric)
    return sp.cluster.hierarchy.complete(D)


def partition_tree_shuffle(indexes, index_mask, partition_tree):
    """ Randomly shuffle the indexes in a way that is consistent with the given partition tree.

    Parameters
    ----------
    indexes: np.array
        The output location of the indexes we want shuffled. Note that len(indexes) should equal index_mask.sum().

    index_mask: np.array
        A bool mask of which indexes we want to include in the shuffled list.

    partition_tree: np.array
        The partition tree we should follow.
    """
    M = len(index_mask)
    #switch = np.random.randn(M) < 0
    _pt_shuffle_rec(partition_tree.shape[0]-1, indexes, index_mask, partition_tree, M, 0)
@jit
def _pt_shuffle_rec(i, indexes, index_mask, partition_tree, M, pos):
    if i < 0:
        # see if we should include this index in the ordering
        if index_mask[i + M]: 
            indexes[pos] = i + M
            return pos + 1
        else:
            return pos
    left = int(partition_tree[i,0] - M)
    right = int(partition_tree[i,1] - M)
    if np.random.randn() < 0:
        pos = _pt_shuffle_rec(left, indexes, index_mask, partition_tree, M, pos)
        pos = _pt_shuffle_rec(right, indexes, index_mask, partition_tree, M, pos)
    else:
        pos = _pt_shuffle_rec(right, indexes, index_mask, partition_tree, M, pos)
        pos = _pt_shuffle_rec(left, indexes, index_mask, partition_tree, M, pos)
    return pos

@jit
def delta_minimization_order(all_masks, max_swap_size=100, num_passes=2):
    order = np.arange(len(all_masks))
    for _ in range(num_passes):
        for length in list(range(2, max_swap_size)): 
            for i in range(1, len(order)-length):
                if _reverse_window_score_gain(all_masks, order, i, length) > 0:
                    _reverse_window(order, i, length)
    return order
@jit
def _reverse_window(order, start, length):
    for i in range(length // 2):
        tmp = order[start + i]
        order[start + i] = order[start + length - i - 1]
        order[start + length - i - 1] = tmp
@jit
def _reverse_window_score_gain(masks, order, start, length):
    forward_score = _mask_delta_score(masks[order[start - 1]], masks[order[start]]) + \
                    _mask_delta_score(masks[order[start + length-1]], masks[order[start + length]])
    reverse_score = _mask_delta_score(masks[order[start - 1]], masks[order[start + length-1]]) + \
                    _mask_delta_score(masks[order[start]], masks[order[start + length]])
    
    return forward_score - reverse_score
@jit
def _mask_delta_score(m1, m2):
    return (m1 ^ m2).sum()


def hclust_ordering(X, metric="sqeuclidean", anchor_first=False):
    """ A leaf ordering is under-defined, this picks the ordering that keeps nearby samples similar.
    """
    
    # compute a hierarchical clustering
    D = sp.spatial.distance.pdist(X, metric)
    cluster_matrix = sp.cluster.hierarchy.complete(D)
    
    # merge clusters, rotating them to make the end points match as best we can
    sets = [[i] for i in range(X.shape[0])]
    for i in range(cluster_matrix.shape[0]):
        s1 = sets[int(cluster_matrix[i,0])]
        s2 = sets[int(cluster_matrix[i,1])]

        # compute distances between the end points of the lists
        d_s1_s2 = pdist(np.vstack([X[s1[-1],:], X[s2[0],:]]), metric)[0]
        d_s1_s2r = pdist(np.vstack([X[s1[-1],:], X[s2[-1],:]]), metric)[0]
        d_s1r_s2 = pdist(np.vstack([X[s1[0],:], X[s2[0],:]]), metric)[0]
        d_s1r_s2r = pdist(np.vstack([X[s1[0],:], X[s2[-1],:]]), metric)[0]
        d_s2_s1 = pdist(np.vstack([X[s2[-1],:], X[s1[0],:]]), metric)[0]
        d_s2_s1r = pdist(np.vstack([X[s2[-1],:], X[s1[-1],:]]), metric)[0]
        d_s2r_s1 = pdist(np.vstack([X[s2[0],:], X[s1[0],:]]), metric)[0]
        d_s2r_s1r = pdist(np.vstack([X[s2[0],:], X[s1[-1],:]]), metric)[0]

        # if we are anchoring the first element to the start of the list then we invalidate orderings
        # that would move that element into a different position
        if anchor_first:
            max_val = max(d_s1_s2, d_s1_s2r, d_s1r_s2, d_s1r_s2r, d_s2_s1, d_s2_s1r, d_s2r_s1, d_s2r_s1r) + 1
            if s1[0] == 0:
                d_s1r_s2 = max_val
                d_s1r_s2r = max_val
                d_s2_s1 = max_val
                d_s2_s1r = max_val
                d_s2r_s1 = max_val
                d_s2r_s1r = max_val
            elif s2[0] == 0:
                d_s1_s2 = max_val
                d_s1_s2r = max_val
                d_s1r_s2 = max_val
                d_s1r_s2r = max_val
                d_s2r_s1 = max_val
                d_s2r_s1r = max_val

        # concatenete the lists in the way the minimizes the difference between
        # the samples at the junction
        best = min(d_s1_s2, d_s1_s2r, d_s1r_s2, d_s1r_s2r, d_s2_s1, d_s2_s1r, d_s2r_s1, d_s2r_s1r)
        if best == d_s1_s2:
            sets.append(s1 + s2)
        elif best == d_s1_s2r:
            sets.append(s1 + list(reversed(s2)))
        elif best == d_s1r_s2:
            sets.append(list(reversed(s1)) + s2)
        elif best == d_s1r_s2r:
            sets.append(list(reversed(s1)) + list(reversed(s2)))
        elif best == d_s2_s1:
            sets.append(s2 + s1)
        elif best == d_s2_s1r:
            sets.append(s2 + list(reversed(s1)))
        elif best == d_s2r_s1:
            sets.append(list(reversed(s2)) + s1)
        elif best == d_s2r_s1r:
            sets.append(list(reversed(s2)) + list(reversed(s1)))
    
    return sets[-1]

    