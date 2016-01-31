import numpy as np
import time
import logging
import hashlib
import base64

from collections import defaultdict
from sys import version_info

if version_info.major >= 3:
    basestring = str

log = logging.getLogger('trimesh')
log.addHandler(logging.NullHandler())   
    
# included here so util has only standard library imports
_TOL_ZERO = 1e-12

def unitize(points, check_valid=False):
    '''
    Flexibly turn a list of vectors into a list of unit vectors.
    
    Arguments
    ---------
    points:       (n,m) or (j) input array of vectors. 
                  For 1D arrays, points is treated as a single vector
                  For 2D arrays, each row is treated as a vector
    check_valid:  boolean, if True enables valid output and checking

    Returns
    ---------
    unit_vectors: (n,m) or (j) length array of unit vectors

    valid:        (n) boolean array, output only if check_valid.
                   True for all valid (nonzero length) vectors, thus m=sum(valid)
    '''
    points       = np.array(points)
    axis         = len(points.shape) - 1
    length       = np.sum(points ** 2, axis=axis) ** .5
    if check_valid:
        valid = np.greater(length, _TOL_ZERO)
        if axis == 1: 
            unit_vectors = (points[valid].T / length[valid]).T
        elif len(points.shape) == 1 and valid: 
            unit_vectors = points / length
        else:         
            unit_vectors = []
        return unit_vectors, valid        
    else: 
        unit_vectors = (points.T / length).T
    return unit_vectors

def transformation_2D(offset=[0.0,0.0], theta=0.0):
    '''
    2D homogeonous transformation matrix
    '''
    T = np.eye(3)
    s = np.sin(theta)
    c = np.cos(theta)

    T[0,0:2] = [ c, s]
    T[1,0:2] = [-s, c]
    T[0:2,2] = offset
    return T

def euclidean(a, b):
    '''
    Euclidean distance between vectors a and b
    '''
    return np.sum((np.array(a) - b)**2) ** .5

def is_file(obj):
    return hasattr(obj, 'read')

def is_string(obj):
    return isinstance(obj, basestring)

def is_dict(obj):
    return isinstance(obj, dict)

def is_sequence(obj):
    '''
    Returns True if obj is a sequence.
    '''
    seq = (not hasattr(obj, "strip") and
           hasattr(obj, "__getitem__") or
           hasattr(obj, "__iter__"))

    seq = seq and not isinstance(obj, dict)
    # numpy sometimes returns objects that are single float64 values
    # but sure look like sequences, so we check the shape
    if hasattr(obj, 'shape'):
        seq = seq and obj.shape != ()
    return seq

def make_sequence(obj):
    '''
    Given an object, if it is a sequence return, otherwise
    add it to a length 1 sequence and return.

    Useful for wrapping functions which sometimes return single 
    objects and other times return lists of objects. 
    '''
    if is_sequence(obj): return np.array(obj)
    else:                return np.array([obj])

def vector_to_spherical(cartesian):
    '''
    Convert a set of cartesian points to (n,2) spherical vectors
    '''
    x,y,z = np.array(cartesian).T
    # cheat on divide by zero errors
    x[np.abs(x) < _TOL_ZERO] = _TOL_ZERO
    spherical = np.column_stack((np.arctan(y/x),
                                 np.arccos(z)))
    return spherical

def spherical_to_vector(spherical):
    '''
    Convert a set of (n,2) spherical vectors to (n,3) vectors
    '''
    theta, phi = np.array(spherical).T
    st, ct = np.sin(theta), np.cos(theta)
    sp, cp = np.sin(phi),   np.cos(phi)
    vectors = np.column_stack((ct*sp,
                               st*sp,
                               cp))
    return vectors

def diagonal_dot(a, b):
    '''
    Dot product by row of a and b.

    Same as np.diag(np.dot(a, b.T)) but without the monstrous 
    intermediate matrix.
    '''
    result = (np.array(a)*b).sum(axis=1)
    return result

def three_dimensionalize(points, return_2D=True):
    '''
    Given a set of (n,2) or (n,3) points, return them as (n,3) points

    Arguments
    ----------
    points:    (n, 2) or (n,3) points
    return_2D: boolean flag

    Returns
    ----------
    if return_2D: 
        is_2D: boolean, True if points were (n,2)
        points: (n,3) set of points
    else:
        points: (n,3) set of points
    '''
    points = np.array(points)
    shape = points.shape
 
    if len(shape) != 2:
        raise ValueError('Points must be 2D array!')

    if shape[1] == 2:
        points = np.column_stack((points, np.zeros(len(points))))
        is_2D = True
    elif shape[1] == 3:
        is_2D = False
    else:
        raise ValueError('Points must be (n,2) or (n,3)!')

    if return_2D: 
        return is_2D, points
    return points

def grid_arange_2D(bounds, step):
    '''
    Return a 2D grid with specified spacing

    Arguments
    ---------
    bounds: (2,2) list of [[minx, miny], [maxx, maxy]]
    step:   float, separation between points
    
    Returns
    -------
    grid: (n, 2) list of 2D points
    '''
    x_grid = np.arange(*bounds[:,0], step = step)
    y_grid = np.arange(*bounds[:,1], step = step)
    grid   = np.dstack(np.meshgrid(x_grid, y_grid)).reshape((-1,2))
    return grid

def grid_linspace_2D(bounds, count):
    '''
    Return a count*count 2D grid

    Arguments
    ---------
    bounds: (2,2) list of [[minx, miny], [maxx, maxy]]
    count:  int, number of elements on a side
    
    Returns
    -------
    grid: (count**2, 2) list of 2D points
    '''
    x_grid = np.linspace(*bounds[:,0], count = count)
    y_grid = np.linspace(*bounds[:,1], count = count)
    grid   = np.dstack(np.meshgrid(x_grid, y_grid)).reshape((-1,2))
    return grid

def replace_references(data, reference_dict):
    # Replace references in place
    view = np.array(data).view().reshape((-1))
    for i, value in enumerate(view):
        if value in reference_dict:
            view[i] = reference_dict[value]
    return view

def multi_dict(pairs):
    '''
    Given a set of key value pairs, create a dictionary. 
    If a key occurs multiple times, stack the values into an array.

    Can be called like the regular dict(pairs) constructor

    Arguments
    ----------
    pairs: (n,2) array of key, value pairs

    Returns
    ----------
    result: dict, with all values stored (rather than last with regular dict)

    '''
    result = defaultdict(list)
    for k, v in pairs:
        result[k].append(v)
    return result

def tolist_dict(data):
    def tolist(item):
        if hasattr(item, 'tolist'):
            return item.tolist()
        else:
            return item
    result = {k:tolist(v) for k,v in data.items()}
    return result
    
def is_binary_file(file_obj):
    '''
    Returns True if file has non-ASCII characters (> 0x7F, or 127)
    Should work in both Python 2 and 3
    '''
    start  = file_obj.tell()
    fbytes = file_obj.read(1024)
    file_obj.seek(start)
    is_str = isinstance(fbytes, str)
    for fbyte in fbytes:
        if is_str: code = ord(fbyte)
        else:      code = fbyte
        if code > 127: return True
    return False

def decimal_to_digits(decimal, min_digits=None):
    digits = abs(int(np.log10(decimal)))
    if min_digits is not None:
        digits = np.clip(digits, min_digits, 20)
    return digits

def md5_object(obj):
    '''
    If an object is hashable, return the hex string of the MD5.
    '''
    hasher = hashlib.md5()
    hasher.update(obj)
    hashed = hasher.hexdigest()
    return hashed

def attach_to_log(log_level = logging.DEBUG, 
                  blacklist = ['TerminalIPythonApp','PYREADLINE']):
    '''
    Attach a stream handler to all loggers.
    '''
    try: 
        from colorlog import ColoredFormatter
        formatter = ColoredFormatter(
            ("%(log_color)s%(levelname)-8s%(reset)s " + 
             "%(filename)17s:%(lineno)-4s  %(blue)4s%(message)s"),
            datefmt = None,
            reset   = True,
            log_colors = {'DEBUG':    'cyan',
                          'INFO':     'green',
                          'WARNING':  'yellow',
                          'ERROR':    'red',
                          'CRITICAL': 'red' } )
    except ImportError: 
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s (%(filename)s:%(lineno)3s) %(message)s", 
            "%Y-%m-%d %H:%M:%S")
    handler_stream = logging.StreamHandler()
    handler_stream.setFormatter(formatter)
    handler_stream.setLevel(log_level)

    for logger in logging.Logger.manager.loggerDict.values():
        if logger.__class__.__name__ != 'Logger': 
            continue
        if logger.name in blacklist:
            continue
        logger.addHandler(handler_stream)
        logger.setLevel(log_level)
    np.set_printoptions(precision=5, suppress=True)
    
def tracked_array(array, dtype=None):
    '''
    Properly subclass a numpy ndarray to track changes. 
    '''
    result = np.ascontiguousarray(array).view(TrackedArray)
    if dtype is None: 
        return result
    return result.astype(dtype)


class TrackedArray(np.ndarray):
    '''
    Track changes in a numpy ndarray.

    Methods
    ----------
    md5: returns hexadecimal string of md5 of array
    '''

    def __array_finalize__(self, obj):
        '''
        Sets a modified flag on every TrackedArray
        This flag will be set on every change, as well as during copies
        and certain types of slicing. 
        '''
        self._modified = True
        if isinstance(obj, type(self)):
            obj._modified = True
            
    def md5(self):
        '''
        Return an MD5 hash of the current array in hexadecimal string form. 
        
        This is quite fast; on a modern i7 desktop a (1000000,3) floating point 
        array was hashed reliably in .03 seconds. 
        
        This is only recomputed if a modified flag is set which may have false 
        positives (forcing an unnecessary recompute) but will not have false 
        negatives which would return an incorrect hash. 
        '''

        if self._modified or not hasattr(self, '_hashed'):
            self._hashed = md5_object(self)
        self._modified = False
        return self._hashed

    def __hash__(self):
        '''
        Hash is required to return an int, so we convert the hex string to int.
        '''
        return int(self.md5(), 16)
        
    def __setitem__(self, i, y):
        self._modified = True
        super(self.__class__, self).__setitem__(i, y)

    def __setslice__(self, i, j, y):
        self._modified = True
        super(self.__class__, self).__setslice__(i, j, y)

class Cache:
    '''
    Class to cache values until an id function changes.
    '''
    def __init__(self, id_function):
        self._id_function = id_function
        self.id_current   = None
        self._lock = 0
        self.cache = {}
        
    def get(self, key):
        '''
        Get a key from the cache.

        If the key is unavailable or the cache has been invalidated returns None.
        '''
        self.verify()
        if key in self.cache: 
            return self.cache[key]
        return None
        
    def verify(self):
        '''
        Verify that the cached values are still for the same value of id_function, 
        and delete all stored items if the value of id_function has changed. 
        '''
        id_new = self._id_function()
        if (self._lock == 0) and (id_new != self.id_current):
            if len(self.cache) > 0:
                log.warn('Clearing cache of %d items', len(self.cache))
            self.clear()
            self.id_set()

    def clear(self):
        '''
        Remove all elements in the cache. 
        '''
        self.cache = {}

    def update(self, items):
        '''
        Update the cache with a set of key, value pairs without checking id_function.
        '''
        self.cache.update(items)
        self.id_set()
       
    def id_set(self):
        self.id_current = self._id_function()

    def set(self, key, value):
        self.verify()
        self.cache[key] = value
        return value
        
    def __contains__(self, key):
        self.verify()
        return key in self.cache

    def __enter__(self):
        self._lock += 1
        
    def __exit__(self, *args):
        self._lock -= 1
        self.id_current = self._id_function()

def stack_lines(indices):
    return np.column_stack((indices[:-1],
                            indices[1:])).reshape((-1,2))

def append_faces(vertices_seq, faces_seq): 
    '''
    Given a sequence of zero- indexed faces and vertices,
    combine them into a single (n,3) list of faces and (m,3) vertices

    Arguments
    ---------
    vertices_seq: (n) sequence of (m,d) vertex arrays
    faces_seq     (n) sequence of (p,j) faces, zero indexed
                  and referencing their counterpoint vertices

    '''
    vertices_len = np.array([len(i) for i in vertices_seq])
    face_offset  = np.append(0, np.cumsum(vertices_len)[:-1])
    
    for offset, faces in zip(face_offset, faces_seq):
        faces += offset

    vertices = np.vstack(vertices_seq)
    faces    = np.vstack(faces_seq)

    return vertices, faces

def array_to_base64(array, dtype=None):
    '''
    Export a numpy array to a compact serializable dictionary.

    Arguments
    ---------
    array: numpy array
    dtype: optional, what dtype should array be encoded with.

    Returns
    ---------
    encoded: dict with keys: 
                 dtype: string of dtype
                 shape: int tuple of shape
                 base64: base64 encoded string of flat array
    '''
    array = np.asanyarray(array)
    shape = array.shape
    # ravel also forces contiguous
    flat  = np.ravel(array)
    if dtype is None:
        dtype = array.dtype
    encoded = {'dtype'  : np.dtype(dtype).str,
               'shape'  : shape,
               'base64' : base64.b64encode(flat.astype(dtype))}
    return encoded

def base64_to_array(encoded):
    '''
    Turn a dictionary with base64 encoded strings back into a numpy array.

    Arguments
    ----------
    encoded: dict with keys: 
                 dtype: string of dtype
                 shape: int tuple of shape
                 base64: base64 encoded string of flat array

    Returns
    ----------
    array: numpy array
    '''
    shape = encoded['shape']
    dtype = np.dtype(encoded['dtype'])
    array = np.fromstring(base64.b64decode(encoded['base64']), 
                          dtype).reshape(shape)

    return array
