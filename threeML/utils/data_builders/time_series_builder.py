import numpy as np

from threeML.utils.data_builders.time_series_builder import SpectrumHelper
from threeML.utils.time_series.time_series import TimeSeries
from threeML.io.file_utils import file_existing_and_readable
from threeML.plugins.OGIP.pha import PHAII
from threeML.exceptions.custom_exceptions import custom_warnings

from threeML.plugins.OGIPLike import OGIPLike
from threeML.plugins.OGIP.pha import PHAWrite
from threeML.utils.stats_tools import Significance
from threeML.plugins.spectrum.binned_spectrum import BinnedSpectrum, BinnedSpectrumWithDispersion
from threeML.plugins.spectrum.pha_spectrum import PHASpectrumSet
from threeML.utils.data_builders.fermi.gbm_data import GBMTTEFile, GBMCdata
from threeML.utils.data_builders.fermi.lat_data import LLEFile

from threeML.utils.time_series.eventlist import EventListWithDeadTime, EventListWithLiveTime
from threeML.utils.time_series.binned_spectrum_series import BinnedSpectrumSeries
from threeML.plugins.OGIP.response import InstrumentResponse, InstrumentResponseSet, OGIPResponse
from threeML.plugins.SpectrumLike import SpectrumLike
from threeML.plugins.DispersionSpectrumLike import DispersionSpectrumLike

import copy
import re
import astropy.io.fits as fits


class BinningMethodError(RuntimeError):
    pass


class TimeSeriesBuilder(object):


    def __init__(self, name, time_series,response=None,
                 poly_order=-1, unbinned=True, verbose=True, restore_poly_fit=None):


        assert isinstance(time_series, TimeSeries), "must be a TimeSeries instance"

        self._name = name

        self._time_series = time_series # type: TimeSeries

        if response is not None:

            assert isinstance(response, InstrumentResponse) or isinstance(response, InstrumentResponseSet), 'Response must be an instance of InstrumentResponse'



        if isinstance(response, InstrumentResponseSet):

            # we have a weighted response
            self._rsp_is_weighted = True
            self._weighted_rsp = response

            # just get a dummy response for the moment

            self._response = response.weight_by_counts('0-1')

        else:

            self._rsp_is_weighted = False
            self._weighted_rsp = None

            self._response = response

        self._verbose = verbose

        self._observed_spectrum = None
        self._background_spectrum = None

        self._time_series.poly_order = poly_order


        self._default_unbinned = unbinned

        if restore_poly_fit is not None:

            if file_existing_and_readable(restore_poly_fit):
                self._time_series.restore_fit(restore_poly_fit)

                # In theory this will automatically get the poly counts if a
                # time interval already exists

                if self._response is None:

                    self._background_spectrum = BinnedSpectrum.from_time_series(self._time_series, use_poly=True)

                else:

                    self._background_spectrum = BinnedSpectrumWithDispersion.from_time_series(self._time_series, self._response, use_poly=True)


            else:

                custom_warnings.warn(
                    "Could not find saved background %s." % restore_poly_fit)


        
        

    def _output(self):

        pass
        #super_out = super(EventListLike, self)._output()
        #return super_out.append(self._time_series._output())

    def __set_poly_order(self, value):
        """Background poly order setter """

        self._time_series.poly_order = value

    def ___set_poly_order(self, value):
        """ Indirect poly order setter """

        self.__set_poly_order(value)

    def __get_poly_order(self):
        """ Get poly order """
        return self._time_series.poly_order

    def ___get_poly_order(self):
        """ Indirect poly order getter """

        return self.__get_poly_order()

    background_poly_order = property(___get_poly_order, ___set_poly_order,
                                     doc="Get or set the background polynomial order")

    def set_active_time_interval(self, *intervals, **kwargs):
        """
        Set the time interval to be used during the analysis.
        For now, only one interval can be selected. This may be
        updated in the future to allow for self consistent time
        resolved analysis.
        Specified as 'tmin-tmax'. Intervals are in seconds. Example:

        set_active_time_interval("0.0-10.0")

        which will set the energy range 0-10. seconds.
        :param options:
        :param intervals:
        :return:
        """

        self._time_series.set_active_time_intervals(*intervals)

        # extract a spectrum

        if self._response is None:

            self._observed_spectrum = BinnedSpectrum.from_time_series(self._time_series, use_poly=False)

        else:

            if self._rsp_is_weighted:

                self._response = self._weighted_rsp.weight_by_counts(*intervals)


            self._observed_spectrum = BinnedSpectrumWithDispersion.from_time_series(self._time_series, self._response, use_poly=False)



        self._active_interval = intervals

        if self._time_series.poly_fit_exists:

            if self._response is None:

                self._background_spectrum = BinnedSpectrum.from_time_series(self._time_series, use_poly=True)

            else:

                self._background_spectrum = BinnedSpectrumWithDispersion.from_time_series(self._time_series, self._response, use_poly=True)


        self._tstart = self._time_series.time_intervals.absolute_start_time
        self._tstop = self._time_series.time_intervals.absolute_stop_time

        #return_ogip = False

        # if 'return_ogip' in kwargs:
        #     return_ogip = bool(kwargs.pop('return_ogip'))
        #
        # if return_ogip:
        #     # I really do not like this at the moment
        #     # but I'm assuming there is only one interval selected
        #     new_name = "%s_%s" % (self._name, intervals[0])
        #
        #     new_ogip = OGIPLike(new_name,
        #                         observation=self._observed_pha,
        #                         background=self._bkg_pha,
        #                         response=self._rsp_file,
        #                         verbose=self._verbose,
        #                         spectrum_number=1)
        #
        #     return new_ogip

    def set_background_interval(self, *intervals, **options):
        """
        Set the time interval to fit the background.
        Multiple intervals can be input as separate arguments
        Specified as 'tmin-tmax'. Intervals are in seconds. Example:

        setBackgroundInterval("-10.0-0.0","10.-15.")


        :param *intervals:
        :param **options:

        :return: none

        """
        if 'unbinned' in options:

            unbinned = options.pop('unbinned')
        else:

            unbinned = self._default_unbinned

        self._time_series.set_polynomial_fit_interval(*intervals, unbinned=unbinned)

        # In theory this will automatically get the poly counts if a
        # time interval already exists

        if self._response is None:

            self._background_spectrum = BinnedSpectrum.from_time_series(self._time_series, use_poly=True)

        else:

            # we do not need to worry about the interval of the response if it is a set. only the ebounds are extracted here

            self._background_spectrum = BinnedSpectrumWithDispersion.from_time_series(self._time_series, self._response, use_poly=True)

    def write_pha_from_binner(self, file_name, overwrite=False):
        """

        :param file_name:
        :param overwrite:
        :return:
        """

        # save the original interval if there is one
        old_interval = copy.copy(self._active_interval)
        old_verbose = copy.copy(self._verbose)

        self._verbose = False

        ogip_list = []

        # create copies of the OGIP plugins with the
        # time interval saved.

        for interval in self._time_series.bins:
            self.set_active_time_interval(interval.to_string())

            ogip_list.append(copy.copy(self))

        # write out the PHAII file

        pha_writer = PHAWrite(*ogip_list)

        pha_writer.write(file_name, overwrite=overwrite)

        # restore the old interval

        self.set_active_time_interval(*old_interval)

        self._verbose = old_verbose

    def get_background_parameters(self):
        """
        Returns a pandas DataFrame containing the background polynomial
        coefficients for each cahnnel.

        Returns:

            background dataframe

        """

        return self._time_series.get_poly_info()

    def save_background(self, filename, overwrite=False):
        """

        save the background to and HDF5 file. The filename does not need an extension.
        The filename will be saved as <filename>_bkg.h5



        :param filename: name of file to save
        :param overwrite: to overwrite or not
        :return:
        """

        self._time_series.save_background(filename, overwrite)

    def view_lightcurve(self, start=-10, stop=20., dt=1., use_binner=False):
        # type: (float, float, float, bool) -> None

        """
        :param start:
        :param stop:
        :param dt:
        :param use_binner:

        """

        self._time_series.view_lightcurve(start, stop, dt, use_binner)


    @property
    def bins(self):

        return self._time_series.bins

    def read_bins(self, ttelike):
        """

        Read the temporal bins from another *binned* FermiGBMTTELike instance
        and apply those bins to this instance

        :param ttelike: *binned* FermiGBMTTELike instance
        :return:
        """

        start, stop = ttelike.bins
        self.create_time_bins(start, stop, method='custom')

    def create_time_bins(self, start, stop, method='constant', **options):
        """

        Create time bins from start to stop with a given method (constant, siginificance, bayesblocks, custom).
        Each method has required keywords specified in the parameters. Once created, this can be used as
        a JointlikelihoodSet generator, or as input for viewing the light curve.

        :param start: start of the bins or array of start times for custom mode
        :param stop: stop of the bins or array of stop times for custom mode
        :param method: constant, significance, bayesblocks, custom
        :param use_energy_mask: (optional) use the energy mask when binning (default false)
        :param dt: <constant method> delta time of the
        :param sigma: <significance> sigma level of bins
        :param min_counts: (optional) <significance> minimum number of counts per bin
        :param p0: <bayesblocks> the chance probability of having the correct bin configuration.
        :return:
        """

        if 'use_energy_mask' in options:

            use_energy_mask = options.pop('use_energy_mask')

        else:

            use_energy_mask = False

        if method == 'constant':

            if 'dt' in options:
                dt = float(options.pop('dt'))

            else:

                raise RuntimeError('constant bins requires the dt option set!')

            self._time_series.bin_by_constant(start, stop, dt)


        elif method == 'significance':

            if 'sigma' in options:

                sigma = options.pop('sigma')

            else:

                raise RuntimeError('significance bins require a sigma argument')

            if 'min_counts' in options:

                min_counts = options.pop('min_counts')

            else:

                min_counts = 10

            # should we mask the data

            if use_energy_mask:

                mask = self._mask

            else:

                mask = None

            self._time_series.bin_by_significance(start, stop, sigma=sigma, min_counts=min_counts, mask=mask)


        elif method == 'bayesblocks':

            if 'p0' in options:

                p0 = options.pop('p0')

            else:

                p0 = 0.1

            if 'use_background' in options:

                use_background = options.pop('use_background')

            else:

                use_background = False

            self._time_series.bin_by_bayesian_blocks(start, stop, p0, use_background)

        elif method == 'custom':

            if type(start) is not list:

                if type(start) is not np.ndarray:
                    raise RuntimeError('start must be and array in custom mode')

            if type(stop) is not list:

                if type(stop) is not np.ndarray:
                    raise RuntimeError('stop must be and array in custom mode')

            assert len(start) == len(stop), 'must have equal number of start and stop times'

            self._time_series.bin_by_custom(start, stop)




        else:

            raise BinningMethodError('Only constant, significance, bayesblock, or custom method argument accepted.')

    def get_ogip_from_binner(self):
        """

        Returns a list of ogip_instances corresponding to the
        time intervals created by the binner.

        :return: list of ogip instances for each time interval
        """

        # save the original interval if there is one
        old_interval = copy.copy(self._active_interval)
        old_verbose = copy.copy(self._verbose)

        self._verbose = False

        ogip_list = []

        # create copies of the OGIP plugins with the
        # time interval saved.



        for i, interval in enumerate(self._time_series.bins):
            self.set_active_time_interval(interval.to_string())

            new_name = "%s_%d" % (self._name, i)

            new_ogip = OGIPLike(new_name,
                                observation=self._observed_spectrum,
                                background=self._background_spectrum,
                                response=self._rsp_file,
                                verbose=self._verbose,
                                spectrum_number=1)

            ogip_list.append(new_ogip)

        # restore the old interval

        self.set_active_time_interval(*old_interval)

        self._verbose = old_verbose

        return ogip_list


    def to_spectrumlike(self, from_bins=False):
        """
        return a SpectrumLike or DispersionSpectrumLike plugin
        from the current selections


        :return:
        """



        if self._response is None:

            return SpectrumLike(name=self._name,
                                observation=self._observed_spectrum,
                                background=self._background_spectrum,
                                verbose=self._verbose)

        else:

            return DispersionSpectrumLike(name=self._name,
                                          observation=self._observed_spectrum,
                                          background=self._background_spectrum,
                                          verbose=self._verbose)



    @classmethod
    def from_gbm_tte(cls,name, tte_file, rsp_file, restore_background=None,
                 trigger_time=None,
                 poly_order=-1, unbinned=True, verbose=True):
        """
               A plugin to natively bin, view, and handle Fermi GBM TTE data.
               A TTE event file are required as well as the associated response



               Background selections are specified as
               a comma separated string e.g. "-10-0,10-20"

               Initial source selection is input as a string e.g. "0-5"

               One can choose a background polynomial order by hand (up to 4th order)
               or leave it as the default polyorder=-1 to decide by LRT test

               :param name: name for your choosing
               :param tte_file: GBM tte event file
               :param rsp_file: Associated TTE CSPEC response file
               :param trigger_time: trigger time if needed
               :param poly_order: 0-4 or -1 for auto
               :param unbinned: unbinned likelihood fit (bool)
               :param verbose: verbose (bool)



               """

        #self._default_unbinned = unbinned

        # Load the relevant information from the TTE file

        gbm_tte_file = GBMTTEFile(tte_file)

        # Set a trigger time if one has not been set

        if trigger_time is not None:
            gbm_tte_file.trigger_time = trigger_time

        # Create the the event list

        event_list = EventListWithDeadTime(arrival_times=gbm_tte_file.arrival_times - gbm_tte_file.trigger_time,
                                           energies=gbm_tte_file.energies,
                                           n_channels=gbm_tte_file.n_channels,
                                           start_time=gbm_tte_file.tstart - gbm_tte_file.trigger_time,
                                           stop_time=gbm_tte_file.tstop - gbm_tte_file.trigger_time,
                                           dead_time=gbm_tte_file.deadtime,
                                           first_channel=1,
                                           instrument=gbm_tte_file.det_name,
                                           mission=gbm_tte_file.mission,
                                           verbose=verbose)

        # we need to see if this is an RSP2

        test = re.match('^.*\.rsp2$', rsp_file)

        if test is not None:

            rsp = InstrumentResponseSet.from_rsp2_file(rsp2_file=rsp_file,
                                                                 counts_getter=event_list.counts_over_interval,
                                                                 exposure_getter=event_list.exposure_over_interval,
                                                                 reference_time=gbm_tte_file.trigger_time)



        else:


            rsp = OGIPResponse(rsp_file)




        # pass to the super class

        return cls(name,
                   event_list,
                   response=rsp,
                   poly_order=poly_order,
                   unbinned=unbinned,
                   verbose=verbose,
                   restore_poly_fit=restore_background)



    @classmethod
    def from_gbm_cspec_or_ctime(cls,name, cspec_or_ctime_file, rsp_file, restore_background=None,
                 trigger_time=None,
                 poly_order=-1, verbose=True):
        """
               A plugin to natively bin, view, and handle Fermi GBM TTE data.
               A TTE event file are required as well as the associated response



               Background selections are specified as
               a comma separated string e.g. "-10-0,10-20"

               Initial source selection is input as a string e.g. "0-5"

               One can choose a background polynomial order by hand (up to 4th order)
               or leave it as the default polyorder=-1 to decide by LRT test

               :param name: name for your choosing
               :param tte_file: GBM tte event file
               :param rsp_file: Associated TTE CSPEC response file
               :param trigger_time: trigger time if needed
               :param poly_order: 0-4 or -1 for auto
               :param unbinned: unbinned likelihood fit (bool)
               :param verbose: verbose (bool)



               """

        #self._default_unbinned = unbinned

        # Load the relevant information from the TTE file

        cdata = GBMCdata(cspec_or_ctime_file,rsp_file)



        #Set a trigger time if one has not been set

        if trigger_time is not None:
            cdata.trigger_time = trigger_time

        # Create the the event list

        event_list = BinnedSpectrumSeries(cdata.spectrum_set,
                                          first_channel=1,
                                          mission='Fermi',
                                          instrument=cdata.det_name,
                                          verbose=verbose)

        # we need to see if this is an RSP2

        test = re.match('^.*\.rsp2$', rsp_file)

        if test is not None:

            rsp = InstrumentResponseSet.from_rsp2_file(rsp2_file=rsp_file,
                                                                 counts_getter=event_list.counts_over_interval,
                                                                 exposure_getter=event_list.exposure_over_interval,
                                                                 reference_time=cdata.trigger_time)



        else:


            rsp = OGIPResponse(rsp_file)




        # pass to the super class

        return cls(name,
                   event_list,
                   response=rsp,
                   poly_order=poly_order,
                   unbinned=False,
                   verbose=verbose,
                   restore_poly_fit=restore_background)




    @classmethod
    def from_lat_lle(cls):

        pass

    @classmethod
    def from_polar(cls):

        pass

