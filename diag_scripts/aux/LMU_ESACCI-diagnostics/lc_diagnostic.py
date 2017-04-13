import os
import subprocess
import numpy as np
import matplotlib.pyplot as plt
from netCDF4 import Dataset
from geoval.core.mapping import SingleMap
from diagnostic import BasicDiagnostics


class LandCoverDiagnostic(BasicDiagnostics):
    """
    class to implement soil moisture diagnostics,
    like e.g. global means, global differences, RMSD etc.

    TODO implement testing for this diagnostic

    """

    def __init__(self, **kwargs):
        super(LandCoverDiagnostic, self).__init__(**kwargs)

        self._project_info = {}
        self._modtype = None
        self._reftype = None
        self._plot_dir = '.' + os.sep
        self._work_dir = '.' + os.sep

        self._vartype = 'land cover'  # default value as there must be one
        self.output_type = 'png'  # default ouput file type
        self._changed = False

    def run_diagnostic(self):
        """
        running the diagnostics
        """

        if '_ref_data' not in self.__dict__.keys():
            return

        super(LandCoverDiagnostic, self).run_diagnostic()

        self._specific_diag(single_years=self.cfg.single_years)

    def _specific_diag(self, single_years=True):
        """
        Diagnostic management
        """

        if single_years:
            self._year_uncertainty()

    def write_data(self, plot=True):
        """
        write data
        """
        if '_ref_data' not in self.__dict__.keys():
            return

        super(LandCoverDiagnostic, self).write_data()

        if self.cfg.regionalization and '_regions' not in self.__dict__.keys():
            self._regions = self._mod_data.get_regions(
                self._reg_shape, self.cfg.shapeNames - 1)
            self._write_regionalization_header()
            print "this should not be calculated here"

        if '_yu_data' in self.__dict__.keys():

            for yu in self._yu_data.keys():
                # generate map plots for years
                self._plot_yearly_maps(self._yu_data[yu], yu)
                if self.cfg.regionalization:
                    [self._yu_data[yu][n].get_shape_statistics(self._regions)
                     for n in np.arange(3)]
                    self._write_shape_statistics(
                        self._yu_data[yu][0].regionalized,
                        'mean_m' + str(self.cfg.std_factor) + 'std_' + yu,
                        self.modname + "_" + self.refname)
                    self._write_shape_statistics(
                        self._yu_data[yu][1].regionalized,
                        'mean_' + yu,
                        self.modname + "_" + self.refname)
                    self._write_shape_statistics(
                        self._yu_data[yu][2].regionalized,
                        'mean_p' + str(self.cfg.std_factor) + 'std_' + yu,
                        self.modname + "_" + self.refname)
        else:
            print 'No yearly data to plot!'

    def _year_uncertainty(self):
        """ get data for uncertainty plot """

        # comparison for the single years
        ref_save = self._ref_data.copy()
        mod_save = self._mod_data.copy()

        loc_dict = dict()

        years = [x.year for x in self._ref_data.date]

        # only the middle year
        theseyears = [years[int(len(years) / 2)]]

        print(theseyears)

        for y in theseyears:

            loc_dict[str(y)] = []

            mod_data_std = self._mod_data.copy()
            mod_data_std.data = mod_data_std.data.std(axis=0)

            low_d_r = mod_data_std.copy()
            mid_d_r = mod_data_std.copy()
            high_d_r = mod_data_std.copy()

            low_d = self._mod_data.data - self.cfg.std_factor * \
                mod_data_std.data - self._ref_data.data.mean(axis=0)
            low_d.mask = (self._mod_data.data.mask + mod_data_std.data.mask +
                          self._ref_data.data.mask).astype(bool)
            low_d_r.data = low_d
            loc_dict[str(y)].insert(0, low_d_r)

            mid_d = self._mod_data.data - self._ref_data.data.mean(axis=0)
            mid_d.mask = (self._mod_data.data.mask + mod_data_std.data.mask +
                          self._ref_data.data.mask).astype(bool)
            mid_d_r.data = mid_d
            loc_dict[str(y)].insert(1, mid_d_r)

            high_d = self._mod_data.data + self.cfg.std_factor * \
                mod_data_std.data - self._ref_data.data.mean(axis=0)
            high_d.mask = (self._mod_data.data.mask +
                           mod_data_std.data.mask +
                           self._ref_data.data.mask).astype(bool)
            high_d_r.data = high_d
            loc_dict[str(y)].insert(2, high_d_r)

            self._ref_data = ref_save.copy()
            self._mod_data = mod_save.copy()

        self._yu_data = loc_dict

    def _plot_yearly_maps(self, low_mid_high, year):
        """
        plot kendall's tau trend correlations
        """
        f = plt.figure(figsize=(30, 6))
        ax1 = f.add_subplot(131)
        ax2 = f.add_subplot(132)
        ax3 = f.add_subplot(133)

        def submap(data, ax, title, vmin, vmax, cmap,
                   ctick={'ticks': None, 'labels': None}):
            Map = SingleMap(data,
                            backend=self.plot_backend,
                            show_statistic=True,
                            savefile=None,
                            ax=ax,
                            show_unit=False)
            Map.plot(title=title,
                     show_zonal=False,
                     show_histogram=False,
                     show_timeseries=False,
                     nclasses=self.plot_nclasses,
                     colorbar_orientation=self.plot_cborientation,
                     show_colorbar=self.plot_cbshow,
                     cmap=cmap,
                     vmin=min(self.cfg.mima_single_year),
                     vmax=max(self.cfg.mima_single_year),
                     proj_prop=self.cfg.projection,
                     ctick_prop=ctick,
                     drawparallels=True,
                     titlefontsize=self.plot_tfont)

        submap(low_mid_high[0], ax=ax1, title="mean - " +
               str(self.cfg.std_factor) + "*std", vmin=-1, vmax=1, cmap='RdBu')
        submap(low_mid_high[1], ax=ax2, title="mean",
               vmin=0, vmax=1, cmap='RdBu')
        submap(low_mid_high[2], ax=ax3, title="mean + " +
               str(self.cfg.std_factor) + "*std", vmin=-1, vmax=1, cmap='RdBu')
        f.suptitle("Difference between " + self.modname + " and " +
                   self.refname + " within the range of the " +
                   str(self.cfg.std_factor) +
                   "th standard deviation of the model for years around " +
                   year)  # TODO get the year range right

        oname = self._get_output_rootname() + "_diff_std_" + year + \
            '.' + self.output_type
        if os.path.exists(oname):
            os.remove(oname)
        f.savefig(oname, dpi=self.plot_dpi)

        plt.close(f.number)  # close figure for memory reasons!
        del f

    def _load_model_data(self):
        """ load all land cover model data """

        edited = False

        newfile = self._mod_file + ".T63built.nc"
        newfile = newfile.split("/")
        newdir = (self._work_dir if self._work_dir[-1] ==
                  os.sep else self._work_dir + os.sep) + "AUX_Files_lc_ESACCI"
        newfile = newdir + os.sep + newfile[-1]

        mod_info = Dataset(self._mod_file)
        lat = mod_info.dimensions['lat'].size
        lon = mod_info.dimensions['lon'].size
        mod_info.close()

        if not ((lat == 96 and lon == 192) or
                (lat == 6 and lon == 12) or
                (lat == 18 and lon == 36)):  # TODO add diffs

            if not os.path.exists(newfile):
                tempfile = self._aggregate_resolution(
                    self._mod_file, "T63", remove=False)
                subprocess.call(["mkdir", newdir])
                subprocess.call(['cp', tempfile, newfile])
                os.remove(tempfile)

            self._mod_file_E = newfile
            edited = True

        # load data
        self._mod_data = self._load_cmip_generic(
            self._mod_file_E if edited else self._mod_file, self.var)
#        self._mod_data.data=np.nan_to_num(self._mod_data.data)

    def _load_observation_data(self):
        """ load obs data """
        newfile = self._ref_file + ".T63built.nc"
        newfile = newfile.split("/")
        newdir = (self._work_dir if self._work_dir[-1] ==
                  os.sep else self._work_dir + os.sep) + "AUX_Files_lc_ESACCI"
        newfile = newdir + os.sep + newfile[-1]

        mod_info = Dataset(self._ref_file)
        lat = mod_info.dimensions['lat'].size
        lon = mod_info.dimensions['lon'].size
        mod_info.close()

        if not ((lat == 96 and lon == 192) or
                (lat == 6 and lon == 12) or
                (lat == 18 and lon == 36)):  # TODO add diffs
            if not os.path.exists(newfile):
                tempfile = self._aggregate_resolution(
                    self._ref_file, "T63", remove=False)
                subprocess.call(["mkdir", newdir])
                subprocess.call(['cp', tempfile, newfile])
                os.remove(tempfile)

            self._ref_file = newfile

        if self.var in ["baresoilFrac", "grassNcropFrac", "shrubNtreeFrac"]:
            self._ref_data = self._load_cci_generic(self._ref_file, self.var)
#            self._ref_data.data=np.nan_to_num(self._ref_data.data)
        else:
            assert False, 'Not supported yet'
