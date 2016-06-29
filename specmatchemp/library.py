"""
@filename library.py

Defines the library class which will be used for matching
"""

import datetime

import numpy as np
import pandas as pd
import h5py

LIB_COLS = ['lib_index','cps_name', 'obs', 'lib_obs', 'Teff', 'u_Teff', 'radius', 'u_radius', 
            'logg', 'u_logg', 'feh', 'u_feh', 'mass', 'u_mass', 'age', 'u_age', 
            'vsini', 'source', 'source_name']
FLOAT_TOL = 1e-3

class Library():
    """Library class

    This object is a container for the library spectrum and stellar 
    parameters for the library stars. The library is indexed using
    the library_index column.

    Args: 
        library_params (pd.DataFrame): Pandas DataFrame containing
            the parameters for the library stars. It should have
            the columns specified in LIB_COLS, although values can
            be np.nan. The library_index of each row should
            be the index of the specturm in library_spectra.

        wav (np.ndarray): Wavelength scale for the library spectra.

        library_spectra (np.ndarray): 3D array containing the library
            spectra ordered according to the index column.
            Each entry contains the spectrum and its uncertainty.

        header (dict): (optional) Any additional metadata to store
            with the library.

        wavlim (2-element iterable): (optional) The upper and lower
            wavelength limits to be read.
    """
    target_chunk_bytes = 100e3  # Target number of bytes per chunk

    def __init__(self, wav, library_spectra=None, library_params=None, header={}, wavlim=None):
        """
        Creates a fully-formed library from a given set of spectra.
        """
        # If no spectra or params included, create empty library
        if library_spectra is None or library_params is None:
            self.library_params = pd.DataFrame(columns=LIB_COLS)
            self.wav = wav
            self.library_spectra = np.empty((0, 2, len(wav)))
            self.header = {'date_created': str(datetime.date.today())}
            self.wavlim = wavlim
            return

        # otherwise we need to include the provided tables
        # ensure that parameter table has the right columns
        for col in LIB_COLS:
            assert col in library_params.columns, \
                "{0} required in parameter table".format(col)

        # ensure that parameter table, library spectra have same length.
        num_spec = len(library_spectra)
        assert len(library_params) == num_spec,    \
            "Error: Length of parameter table and library spectra are not equal."
        # ensure that all indices in library_params can be found in library_spectra
        for i, row in library_params.iterrows():
            assert i < num_spec,     \
            "Error: Index {0:d} is out of bounds in library_spectra".format(i)

        # ensure library_spectra is of right shape
        assert np.shape(library_spectra)[1] == 2 and np.shape(library_spectra)[2] == len(wav), \
            "Error: library_spectra should have shape ({0:d}, 2, {1:d}".format(num_spec, len(wav))

        self.library_params = library_params
        self.wav = wav
        self.library_spectra = library_spectra
        self.header = header
        header['date_created'] = str(datetime.date.today())
        self.wavlim = wavlim

    def insert(self, params, spectrum, u_spectrum):
        """Insert spectrum and associated stellar parameters into library.

        Args:
            params (pd.Series): A row to be added to the library array. It
                should have the fields specified in LIB_COLS.
            spectrum (np.ndarray): Array containing spectrum to be added.
                The spectrum should have been shifted and interpolated onto
                the same wavelength scale as the library.
            u_spectrum (np.ndarray): Array containing uncertainty in spectrum.
        """
        # ensure that parameter table, library spectra have same length.
        assert len(self.library_params) == len(self.library_spectra),    \
            "Error: Length of parameter table and library spectra are not equal."

        # ensure that parameter row has the right columns
        for col in LIB_COLS:
            assert col in params.columns, \
                "{0} required in parameter specification.".format(col)

        # ensure that the provided spectrum has the same number of elements
        # as the wavelength array
        assert len(spectrum) == len(self.wav), \
            "Error: spectrum is not the same length as library wavelength array"

        # add new star to library
        params.lib_index = len(self.library_spectra)
        self.library_params = pd.concat((self.library_params, params), ignore_index=True)
        self.library_spectra = np.vstack((self.library_spectra, [[spectrum, u_spectrum]]))


    def to_hdf(self, paramfile, specfile):
        """
        Saves library as a HDF file

        Args:
            paramfile (str): Path to store star params
            specfile (str): Path to store spectra
        """

        # store params
        self.library_params.to_hdf(paramfile, 'library_params', format='table', mode='w')

        # store spectrum
        with h5py.File(specfile, 'w') as f:
            for key in self.header.keys():
                f.attrs[key] = self.header[key]
            f['wav'] = self.wav

            # Compute chunk size - group wavelenth regions together
            chunk_row = len(self.library_spectra)
            chunk_depth = 2
            chunk_col = int(self.target_chunk_bytes / self.library_spectra[:,:,0].nbytes)
            chunk_size = (chunk_row, chunk_depth, chunk_col)

            print("Storing model spectra with chunks of size {0}".format(chunk_size))
            dset = f.create_dataset('library_spectra', data=self.library_spectra,
                compression='gzip', compression_opts=1, shuffle=True, chunks=chunk_size)

        

    def __str__(self):
        """
        String representation of library
        """
        outstr = "<specmatchemp.library.Library>\n"
        for key, val in self.header.items():
            outstr += "{0}: {1}\n".format(key, val)

        return outstr

    ## Container methods
    def __iter__(self):
        """
        Allow library to be an iterable
        """
        # iterate over the spectrum table
        # iteration over np.ndarray much faster than pd.DataFrame
        self.__it_counter = 0

        return self

    def __next__(self):
        """
        Next item

        Returns:
            params (pd.Series): Stellar parameters for the next star.
            spectrum (np.ndarray): Spectrum for the next star
        """
        if self.__it_counter >= len(self.library_spectra):
            raise StopIteration

        idx = self.__it_counter
        self.__it_counter += 1
        return self.library_params.loc[idx], self.library_spectra[idx]

    def __len__(self):
        """Number of spectra in library.

        Returns:
            Number of spectra stored in library.
        """
        return len(self.library_spectra)

    def __getitem__(self, index):
        """
        Get item at specified library_index

        Args:
            index (int): Library index of desired spectrum.
        """
        # Check if library_index specified is in the container
        if not self.__contains__(index):
            raise KeyError

        return self.library_params.loc[index], self.library_spectra.loc[index]

    def __contains__(self, index):
        """
        Check if specified library_index is filled

        Args:
            index (int): Library index to check
        """
        return index in self.library_params.index

def read_hdf(paramfile, specfile, wavlim=None):
    """
    Reads in a library from a HDF file

    Args:
        paramfile (str): path to h5 file containing star parameters.
        specfile (str): path to h5 file containing spectra.
        wavlim (2-element iterable): (optional) The upper and lower wavelength
            limits to be read.

    Returns:
        lib (library.Library) object
    """
    library_params = pd.read_hdf(paramfile, 'library_params')

    with h5py.File(specfile, 'r') as f:
        header = dict(f.attrs)
        wav = f['wav'][:]

        if wavlim is None:
            library_spectra = f['library_spectra'][:]
        else:
            idxwav, = np.where( (wav > wavlim[0]) & (wav < wavlim[1]))
            idxmin = idxwav[0]
            idxmax = idxwav[-1] + 1 # add 1 to include last index when slicing
            model_spectra = h5['library_spectra'][:,:,idxmin:idxmax]
            wav = wav[idxmin:idxmax]

    lib = Library(wav, library_spectra, library_params, header=header, wavlim=wavlim)
    return lib
