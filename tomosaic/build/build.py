#!/usr/bin/env python
# -*- coding: utf-8 -*-

# #########################################################################
# Copyright (c) 2015, UChicago Argonne, LLC. All rights reserved.         #
#                                                                         #
# Copyright 2015. UChicago Argonne, LLC. This software was produced       #
# under U.S. Government contract DE-AC02-06CH11357 for Argonne National   #
# Laboratory (ANL), which is operated by UChicago Argonne, LLC for the    #
# U.S. Department of Energy. The U.S. Government has rights to use,       #
# reproduce, and distribute this software.  NEITHER THE GOVERNMENT NOR    #
# UChicago Argonne, LLC MAKES ANY WARRANTY, EXPRESS OR IMPLIED, OR        #
# ASSUMES ANY LIABILITY FOR THE USE OF THIS SOFTWARE.  If software is     #
# modified to produce derivative works, such modified software should     #
# be clearly marked, so as not to confuse it with the version available   #
# from ANL.                                                               #
#                                                                         #
# Additionally, redistribution and use in source and binary forms, with   #
# or without modification, are permitted provided that the following      #
# conditions are met:                                                     #
#                                                                         #
#     * Redistributions of source code must retain the above copyright    #
#       notice, this list of conditions and the following disclaimer.     #
#                                                                         #
#     * Redistributions in binary form must reproduce the above copyright #
#       notice, this list of conditions and the following disclaimer in   #
#       the documentation and/or other materials provided with the        #
#       distribution.                                                     #
#                                                                         #
#     * Neither the name of UChicago Argonne, LLC, Argonne National       #
#       Laboratory, ANL, the U.S. Government, nor the names of its        #
#       contributors may be used to endorse or promote products derived   #
#       from this software without specific prior written permission.     #
#                                                                         #
# THIS SOFTWARE IS PROVIDED BY UChicago Argonne, LLC AND CONTRIBUTORS     #
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT       #
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS       #
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL UChicago     #
# Argonne, LLC OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,        #
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,    #
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;        #
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER        #
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT      #
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN       #
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE         #
# POSSIBILITY OF SUCH DAMAGE.                                             #
# #########################################################################

"""
Module for center search
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import logging
import numpy as np
import h5py
import tomopy
import shutil
import os
import time
import six
import sys
import dxchange
try:
    from mpi4py import MPI
except:
    from tomosaic.util.pseudo import pseudo_comm
from tomosaic.misc import *
from tomosaic.merge import *
from tomosaic.register import *
from tomosaic.util import *

logger = logging.getLogger(__name__)

__author__ = ['Rafael Vescovi', 'Ming Du']
__credits__ = "Doga Gursoy"
__copyright__ = "Copyright (c) 2015, UChicago Argonne, LLC."
__docformat__ = 'restructuredtext en'
__all__ = ['build_panorama',
           'total_fusion',
           'reorganize_dir']


try:
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()
    name = MPI.Get_processor_name()
except:
    comm = pseudo_comm()
    rank = 0
    size = 1

PI = 3.1415927


def build_panorama(src_folder, file_grid, shift_grid, frame=0, method='max', method2=None, blend_options={}, blend_options2={},
                   blur=None, color_correction=False, margin=100, data_format='aps_32id', verbose=True):

    t00 = time.time()
    root = os.getcwd()
    os.chdir(src_folder)
    buff = np.zeros([1, 1])
    last_none = False
    if method2 is None:
        for (y, x), value in np.ndenumerate(file_grid):
            print (value)
            if (value != None and frame < g_shapes(value)[0]):
                prj, flt, drk, _ = read_data_adaptive(value, proj=(frame, frame + 1), data_format=data_format)
                prj = tomopy.normalize(prj, flt, drk)
                prj = preprocess(prj, blur=blur)
                t0 = time.time()
                buff = blend(buff, np.squeeze(prj), shift_grid[y, x, :], method=method, color_correction=color_correction, **blend_options)
                internal_print('Rank: {:d}; Frame: {:d}; Pos: ({:d}, {:d}); Method: {:s}; Color Corr.:{:b}; Tile stitched in '
                      '{:.2f} s.'.format(rank, frame, y, x, method, color_correction, time.time()-t0))
                if last_none:
                    buff[margin:, margin:-margin][np.isnan(buff[margin:, margin:-margin])] = 0
                    last_none = False
            else:
                last_none = True
    else:
        for y in range(file_grid.shape[0]):
            temp_grid = file_grid[y:y+1, :]
            temp_shift = np.copy(shift_grid[y:y+1, :, :])
            offset = np.min(temp_shift[:, :, 0])
            temp_shift[:, :, 0] = temp_shift[:, :, 0] - offset
            row_buff = np.zeros([1, 1])
            prj, flt, drk, _ = read_data_adaptive(temp_grid[0, 0], proj=(frame, frame + 1), data_format=data_format)
            prj = tomopy.normalize(prj, flt, drk)
            prj = preprocess(prj, blur=blur)
            row_buff, _ = arrange_image(row_buff, np.squeeze(prj), temp_shift[0, 0, :], order=1)
            for x in range(1, temp_grid.shape[1]):
                value = temp_grid[0, x]
                if (value != None and frame < g_shapes(value)[0]):
                    prj, flt, drk, _ = read_data_adaptive(value, proj=(frame, frame + 1), data_format=data_format)
                    prj = tomopy.normalize(prj, flt, drk)
                    prj = preprocess(prj, blur=blur)
                    t0 = time.time()
                    row_buff = blend(row_buff, np.squeeze(prj), temp_shift[0, x, :], method=method, color_correction=color_correction, **blend_options)
                    if verbose:
                        print('Rank: {:d}; Frame: {:d}; Pos: ({:d}, {:d}); Method: {:s}; Color Corr.:{:b}; Tile stitched in '
                              '{:.2f} s; Max: {}.'.format(rank, frame, y, x, method, color_correction, time.time() - t0, row_buff[np.isfinite(row_buff)].max()))
                    if last_none:
                        row_buff[margin:, margin:-margin][np.isnan(row_buff[margin:, margin:-margin])] = 0
                        last_none = False
                else:
                    last_none = True
            t0 = time.time()
            buff = blend(buff, row_buff, [offset, 0], method=method2, color_correction=False, **blend_options2)
            internal_print('Rank: {:d}; Frame: {:d}; Row: {:d}; Row stitched in {:.2f} s; Max: {}.'.format(rank, frame, y, time.time()-t0, buff[np.isfinite(buff)].max()))
    internal_print('Rank: {:d}; Frame: {:d}; Panorama built in {:.2f} s, Max: {}.'.format(rank, frame, time.time()-t00, buff[np.isfinite(buff)].max()))
    os.chdir(root)
    return buff


def total_fusion(src_folder, dest_folder, dest_fname, file_grid, shift_grid, blend_method='pyramid', blend_method2=None,
                 blend_options={}, blend_options2={}, blur=None, color_correction=False, data_format='aps_32id',
                 dtype='float16'):
    """
    Fuse hdf5 of all tiles in to one single file. MPI is supported.

    Parameters
    ----------
    blend_method: blending algorithm. If blend_method2 is None, the specified algorithm will be applied to both x and y
                  directions by default.
    blend_method2: secondary blending algorithm. If this option is not None, it will be applied for blending in y-
                   direction, while blend_method will be applied for x.
    """

    dest_fname = check_fname_ext(dest_fname, 'h5')

    if rank == 0:
        n_frames, y_cam, x_cam = read_data_adaptive(os.path.join(src_folder, file_grid[0, 0]), shape_only=True, data_format=data_format)
        os.makedirs(os.path.join(dest_folder, 'tmp'))
    else:
        n_frames = None
        y_cam = None
        x_cam = None

    n_frames = comm.bcast(n_frames, root=0)
    y_cam = comm.bcast(y_cam, root=0)
    x_cam = comm.bcast(x_cam, root=0)
    frames_per_rank = int(n_frames / size)

    full_width = int(np.max(shift_grid[:, -1, 1]) + x_cam + 10)
    full_height = int(np.max(shift_grid[-1, :, 0]) + y_cam + 10)

    comm.Barrier()

    t0 = time.time()
    alloc_set = allocate_mpi_subsets(n_frames, size)
    for frame in alloc_set[rank]:
        internal_print('alloc set {:d}'.format(rank))
        internal_print('    Rank: {:d}; current frame: {:d}..'.format(rank, frame))
        t00 = time.time()
        # Skip frames that are already stitched.
        if not os.path.exists(os.path.join(dest_folder, 'tmp', str(frame) + '.tiff')):
            pano = np.zeros((full_height, full_width), dtype=dtype)
            # save_stdout = sys.stdout
            # sys.stdout = open('log', 'w')
            temp = build_panorama(src_folder, file_grid, shift_grid, frame=frame, method=blend_method, method2=blend_method2,
                                  blend_options=blend_options, blend_options2=blend_options2, blur=blur, color_correction=color_correction)
            temp[np.isnan(temp)] = 0
            # sys.stdout = save_stdout
            pano[:temp.shape[0], :temp.shape[1]] = temp.astype(dtype)
            dxchange.write_tiff(pano, os.path.join(dest_folder, 'tmp', str(frame)), dtype='float32', overwrite=True)
        internal_print('    Frame {:d} done in {:.3f} s.'.format(frame, time.time() - t00))
    internal_print('Data built in {:.3f} s.'.format(time.time() - t0))

    internal_print('Writing data into new HDF5 file....')

    if rank == 0:

    comm.Barrier()

    
    origin_dir = os.getcwd()
    os.chdir(src_folder)

    _, _, _, theta = read_data_adaptive(file_grid[0, 0], proj=(0, 1), data_format=data_format)
    theta = np.rad2deg(theta)
    n_frames, y_cam, x_cam = read_data_adaptive(file_grid[0, 0], shape_only=True, data_format=data_format)
    frames_per_rank = int(n_frames/size)

    grp = f.create_group('exchange')
    full_width = int(np.max(shift_grid[:, -1, 1]) + x_cam + 10)
    full_height = int(np.max(shift_grid[-1, :, 0]) + y_cam + 10)
    full_shape = (n_frames, full_height, full_width)
    dset_theta = grp.create_dataset('theta', theta.shape, dtype=theta.dtype, data=theta)
    dset_data = grp.create_dataset('data', full_shape, dtype=dtype)
    dset_flat = grp.create_dataset('data_white', (1, full_height, full_width), dtype=dtype)
    dset_dark = grp.create_dataset('data_dark', (1, full_height, full_width), dtype=dtype)
    dset_flat[:, :, :] = np.ones(dset_flat.shape, dtype=dtype)
    dset_dark[:, :, :] = np.zeros(dset_dark.shape, dtype=dtype)

    internal_print('Started to build full hdf5.')
    t0 = time.time()
    alloc_set = allocate_mpi_subsets(n_frames, size)
    for frame in alloc_set[rank]:
        internal_print('alloc set {:d}'.format(rank))
        internal_print('    Rank: {:d}; current frame: {:d}..'.format(rank, frame))
        t00 = time.time()
        pano = np.zeros((full_height, full_width), dtype=dtype)
        # save_stdout = sys.stdout
        # sys.stdout = open('log', 'w')
        temp = build_panorama('.', file_grid, shift_grid, frame=frame, method=blend_method, method2=blend_method2,
                              blend_options=blend_options, blend_options2=blend_options2, blur=blur, color_correction=color_correction)
        temp[np.isnan(temp)] = 0
        # sys.stdout = save_stdout
        pano[:temp.shape[0], :temp.shape[1]] = temp.astype(dtype)
        dset_data[frame, :, :] = pano
        internal_print('    Frame {:d} done in {:.3f} s.'.format(frame, time.time() - t00))
    internal_print('Data built and written in {:.3f} s.'.format(time.time() - t0))
    # try:
    #     os.remove('trash')
    # except:
    #     print('Please remove trash manually.')
# =======
# not sure what happened here ...


        origin_dir = os.getcwd()
        # os.chdir(src_folder)

        _, _, _, theta = read_data_adaptive(os.path.join(src_folder, file_grid[0, 0]), proj=(0, 1), data_format=data_format)
        theta = np.rad2deg(theta)

        grp = f.create_group('exchange')
        full_shape = (n_frames, full_height, full_width)
        dset_theta = grp.create_dataset('theta', theta.shape, dtype=theta.dtype, data=theta)
        dset_data = grp.create_dataset('data', full_shape, dtype=dtype)
        dset_flat = grp.create_dataset('data_white', (1, full_height, full_width), dtype=dtype)
        dset_dark = grp.create_dataset('data_dark', (1, full_height, full_width), dtype=dtype)
        dset_flat[:, :, :] = np.ones(dset_flat.shape, dtype=dtype)
        dset_dark[:, :, :] = np.zeros(dset_dark.shape, dtype=dtype)
        internal_print('Started to build full hdf5.')
        for frame in range(n_frames):
            pano = dxchange.read_tiff(os.path.join(dest_folder, 'tmp', str(frame) + '.tiff'))
            dset_data[frame, :, :] = pano
        f.close()
        internal_print('Data built and written in {:.3f} s.'.format(time.time() - t0))
        internal_print('Removing temporary folder...')
        shutil.rmtree(os.path.join(dest_folder, 'tmp'))
        internal_print('Done.')
    comm.Barrier()
# >>>>>>> 214f897588dc233c08a7dbccb3e87eb27ecdef95

def reorganize_dir(file_list, raw_ds=(2,4), dtype='float16', **kwargs):
    """
    Reorganize hdf5 files and reorganize directory as:
    ----------------
    /data_raw_1x/1920x1200x4500 x* 12x11
                  /shift_matrix
                 /center_matrix
    /data_raw_2x/960x600x4500     x* 12x11

    /raw_4x/480x300x4500     x* 12x11
    ---------------
    /recon_gridrec_1x

    x* means grid of hdf5 files

    Parameters:
    -----------
    file_list : ndarray
        List of h5 files in the directory.
    convert : int, optional
        Bit of integer the data are to be converted into.
    """

    # TODO: add cdf support
    # downsample
    try:
        f = h5py.File(file_list[0], 'r')
        full_shape = f['exchange/data'].shape
    except:
        f = h5py.File(os.path.join('data_raw_1x', file_list[0]), 'r')
        full_shape = f['exchange/data'].shape
    comm.Barrier()

    for fname in file_list:
        comm.Barrier()
        internal_print('Now processing '+str(fname))
        # make downsampled subdirectories
        for ds in raw_ds:
            # create downsample folder if not existing
            folder_name = 'data_raw_'+str(ds)+'x'
            comm.Barrier()
            if rank == 0:
                if not os.path.exists(folder_name):
                    os.mkdir(folder_name)
            comm.Barrier()
            # move file if downsample level is 1
            if ds == 1:
                if rank == 0:
                    if not os.path.isfile(folder_name+'/'+fname):
                        shutil.move(fname, folder_name+'/'+fname)
                comm.Barrier()
            # otherwise perform downsampling
            else:
                if rank == 0:
                    if not os.path.exists(folder_name):
                        os.mkdir(folder_name)
                comm.Barrier()
                try:
                    o = h5py.File('data_raw_1x/' + fname, 'r')
                except:
                    o = h5py.File(fname, 'r')
                raw = o['exchange/data']
                if rank == 0:
                    if os.path.exists(folder_name+'/'+fname):
                        # internal_print('Warning: File already exists. Continue anyway? (y/n) ')
                        # cont = six.moves.input()
                        # if cont in ['n', 'N']:
                        #     continue
                        # else:
                        internal_print('Old file will be overwritten. '+folder_name+'/' + fname)
                        os.remove(folder_name+'/' + fname)
                    f = h5py.File(folder_name+'/'+fname)
                comm.Barrier()
                if rank != 0:
                    f = h5py.File(folder_name+'/'+fname)
                comm.Barrier()
                dat_grp = f.create_group('exchange')
                dat = dat_grp.create_dataset('data', (full_shape[0], np.floor(full_shape[1]/ds),
                                                          np.floor(full_shape[2]/ds)), dtype=dtype)
                # write downsampled data frame-by-frame
                n_frames = full_shape[0]
                alloc_sets = allocate_mpi_subsets(n_frames, size)
                for frame in alloc_sets[rank]:
                    temp = raw[frame:frame+1, :, :]
                    temp = image_downsample(temp, ds)
                    dat[frame:frame+1, :, :] = temp
                    internal_print('\r    Rank: {:d}, DS: {:d}, at frame {:d}'.format(rank, ds, frame))
                internal_print(' ')

                # downsample flat/dark field data
                comm.Barrier()
                raw = o['exchange/data_white']
                aux_shape = raw.shape
                dat = dat_grp.create_dataset('data_white', (aux_shape[0], np.floor(aux_shape[1]/ds),
                                                                  np.floor(aux_shape[2]/ds)), dtype=dtype)
                comm.Barrier()
                internal_print('    Downsampling whites and darks')
                n_whites = raw.shape[0]
                alloc_sets = allocate_mpi_subsets(n_whites, size)
                for frame in alloc_sets[rank]:
                    temp = raw[frame:frame+1, :, :]
                    temp = image_downsample(temp, ds)
                    dat[frame:frame+1, :, :] = temp
                    internal_print('\r    Rank: {:d}, DS: {:d}, at frame {:d}'.format(rank, ds, frame))

                raw = o['exchange/data_dark']
                aux_shape = raw.shape
                dat = dat_grp.create_dataset('data_dark', (aux_shape[0], np.floor(aux_shape[1]/ds),
                                                           np.floor(aux_shape[2]/ds)), dtype=dtype)
                comm.Barrier()
                n_darks = raw.shape[0]
                alloc_sets = allocate_mpi_subsets(n_darks, size)
                for frame in alloc_sets[rank]:
                    temp = raw[frame:frame+1, :, :]
                    temp = image_downsample(temp, ds)
                    dat[frame:frame+1, :, :] = temp
                    internal_print('\r    Rank: {:d}, DS: {:d}, at frame {:d}'.format(rank, ds, frame))

                comm.Barrier()
                raw = o['exchange/theta']
                dat = dat_grp.create_dataset('theta', shape=raw.shape, data=raw.value)

                comm.Barrier()
                f.close()
                comm.Barrier()
                internal_print('Done file: {:s} DS: {:d}'.format(fname, ds))
