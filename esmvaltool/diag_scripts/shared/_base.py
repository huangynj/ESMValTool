"""Convenience functions for running a diagnostic script."""
import argparse
import contextlib
import glob
import logging
import os
import shutil
import sys
import time
from collections import OrderedDict

import yaml

logger = logging.getLogger(__name__)


def get_plot_filename(basename, cfg):
    """Get a valid path for saving a diagnostic plot.

    Parameters
    ----------
    basename: str
        The basename of the file.
    cfg: dict
        Dictionary with diagnostic configuration.

    Returns
    -------
    str:
        A valid path for saving a diagnostic plot.

    """
    return os.path.join(
        cfg['plot_dir'],
        basename + '.' + cfg['output_file_type'],
    )


def get_diagnostic_filename(basename, cfg, extension='nc'):
    """Get a valid path for saving a diagnostic data file.

    Parameters
    ----------
    basename: str
        The basename of the file.
    cfg: dict
        Dictionary with diagnostic configuration.
    extension: str
        File name extension.

    Returns
    -------
    str:
        A valid path for saving a diagnostic data file.

    """
    return os.path.join(
        cfg['work_dir'],
        basename + '.' + extension,
    )


class ProvenanceLogger(object):
    """Open the provenance logger.

    Parameters
    ----------
    cfg: dict
        Dictionary with diagnostic configuration.

    Example
    -------
        Use as a context manager::

            record = {
                'caption': "This is a nice plot.",
                'statistics': ['mean'],
                'domain': 'global',
                'plot_type': 'zonal',
                'plot_file': '/path/to/result.png',
                'authors': [
                    'first_author',
                    'second_author',
                ],
                'references': [
                    'acknow_project',
                ],
                'ancestors': [
                    '/path/to/input_file_1.nc',
                    '/path/to/input_file_2.nc',
                ],
            }
            output_file = '/path/to/result.nc'

            with ProvenanceLogger(cfg) as provenance_logger:
                provenance_logger.log(output_file, record)

    """

    def __init__(self, cfg):
        """Create a provenance logger."""
        self._log_file = os.path.join(cfg['work_dir'],
                                      'diagnostic_provenance.yml')

        if not os.path.exists(self._log_file):
            self.table = {}
        else:
            with open(self._log_file, 'r') as file:
                self.table = yaml.safe_load(file)

    def log(self, filename, record):
        """Record provenance.

        Parameters
        ----------
        filename: str
            Name of the file containing the diagnostic data.
        record: dict
            Dictionary with the provenance information to be logged.

            Typical keys are:
                - plot_type
                - plot_file
                - caption
                - ancestors
                - authors
                - references

        Note
        ----
            See also esmvaltool/config-references.yml

        """
        if filename in self.table:
            raise KeyError(
                "Provenance record for {} already exists.".format(filename))

        self.table[filename] = record

    def _save(self):
        """Save the provenance log to file."""
        dirname = os.path.dirname(self._log_file)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(self._log_file, 'w') as file:
            yaml.safe_dump(self.table, file)

    def __enter__(self):
        """Enter context."""
        return self

    def __exit__(self, *_):
        """Save the provenance log before exiting context."""
        self._save()


def select_metadata(metadata, **attributes):
    """Select specific metadata describing preprocessed data.

    Parameters
    ----------
    metadata : :obj:`list` of :obj:`dict`
        A list of metadata describing preprocessed data.
    **attributes :
        Keyword arguments specifying the required variable attributes and
        their values.
        Use the value '*' to select any variable that has the attribute.

    Returns
    -------
    :obj:`list` of :obj:`dict`
        A list of matching metadata.

    """
    selection = []
    for attribs in metadata:
        if all(
                a in attribs and (
                    attribs[a] == attributes[a] or attributes[a] == '*')
                for a in attributes):
            selection.append(attribs)
    return selection


def group_metadata(metadata, attribute, sort=None):
    """Group metadata describing preprocessed data by attribute.

    Parameters
    ----------
    metadata : :obj:`list` of :obj:`dict`
        A list of metadata describing preprocessed data.
    attribute : str
        The attribute name that the metadata should be grouped by.
    sort :
        See `sorted_group_metadata`.

    Returns
    -------
    :obj:`dict` of :obj:`list` of :obj:`dict`
        A dictionary containing the requested groups. If sorting is requested,
        an `OrderedDict` will be returned.

    """
    groups = {}
    for attributes in metadata:
        key = attributes.get(attribute)
        if key not in groups:
            groups[key] = []
        groups[key].append(attributes)

    if sort:
        groups = sorted_group_metadata(groups, sort)

    return groups


def sorted_metadata(metadata, sort):
    """Sort a list of metadata describing preprocessed data.

    Sorting is done on strings and is not case sensitive.

    Parameters
    ----------
    metadata : :obj:`list` of :obj:`dict`
        A list of metadata describing preprocessed data.
    sort : :obj:`str` or :obj:`list` of :obj:`str`
        One or more attributes to sort by.

    Returns
    -------
    :obj:`list` of :obj:`dict`
        The sorted list of variable metadata.

    """
    if isinstance(sort, str):
        sort = [sort]

    def normalized_variable_key(attributes):
        """Define a key to sort the list of attributes by."""
        return tuple(str(attributes.get(k, '')).lower() for k in sort)

    return sorted(metadata, key=normalized_variable_key)


def sorted_group_metadata(metadata_groups, sort):
    """Sort grouped metadata.

    Sorting is done on strings and is not case sensitive.

    Parameters
    ----------
    metadata_groups : :obj:`dict` of :obj:`list` of :obj:`dict`
        Dictionary containing the groups of metadata.
    sort : :obj:`bool` or :obj:`str` or :obj:`list` of :obj:`str`
        One or more attributes to sort by or True to just sort the groups but
        not the lists.

    Returns
    -------
    :obj:`OrderedDict` of :obj:`list` of :obj:`dict`
        A dictionary containing the requested groups.

    """
    if sort is True:
        sort = []

    def normalized_group_key(key):
        """Define a key to sort the OrderedDict by."""
        return '' if key is None else str(key).lower()

    groups = OrderedDict()
    for key in sorted(metadata_groups, key=normalized_group_key):
        groups[key] = sorted_metadata(metadata_groups[key], sort)

    return groups


def get_cfg(filename=None):
    """Read diagnostic script configuration from settings.yml."""
    if filename is None:
        filename = sys.argv[1]
    with open(filename) as file:
        cfg = yaml.safe_load(file)
    return cfg


def _get_input_data_files(cfg):
    """Get a dictionary containing all data input files."""
    metadata_files = []
    for filename in cfg['input_files']:
        if os.path.isdir(filename):
            metadata_files.extend(
                glob.glob(os.path.join(filename, '*metadata.yml')))
        elif os.path.basename(filename) == 'metadata.yml':
            metadata_files.append(filename)

    input_files = {}
    for filename in metadata_files:
        with open(filename) as file:
            metadata = yaml.safe_load(file)
            input_files.update(metadata)

    return input_files


@contextlib.contextmanager
def run_diagnostic():
    """Run a Python diagnostic.

    This context manager is the main entry point for most Python diagnostics.

    Example
    -------
    See esmvaltool/diag_scripts/examples/diagnostic.py for an extensive
    example of how to start your diagnostic.

    Basic usage is as follows, add these lines at the bottom of your script::

        def main(cfg):
            # Your diagnostic code goes here.
            print(cfg)

        if __name__ == '__main__':
            with run_diagnostic() as cfg:
                main(cfg)

    The `cfg` dict passed to `main` contains the script configuration that
    can be used with the other functions in this module.

    """
    # Implemented as context manager so we can support clean up actions later
    parser = argparse.ArgumentParser(description="Diagnostic script")
    parser.add_argument('filename', help="Path to settings.yml")
    parser.add_argument(
        '-f',
        '--force',
        help=("Force emptying the output directories"
              "(useful when re-running the script)"),
        action='store_true',
    )
    parser.add_argument(
        '-i',
        '--ignore-existing',
        help=("Force running the script, even if output files exists."
              "(useful when re-running the script, use at your own risk)"),
        action='store_true',
    )
    parser.add_argument(
        '-l',
        '--log-level',
        help=("Set the log-level"),
        choices=['debug', 'info', 'warning', 'error'],
    )
    args = parser.parse_args()

    cfg = get_cfg(args.filename)

    # Set up logging
    if args.log_level:
        cfg['log_level'] = args.log_level

    logging.basicConfig(format="%(asctime)s [%(process)d] %(levelname)-8s "
                        "%(name)s,%(lineno)s\t%(message)s")
    logging.Formatter.converter = time.gmtime
    logging.getLogger().setLevel(cfg['log_level'].upper())

    # Read input metadata
    cfg['input_data'] = _get_input_data_files(cfg)

    logger.info("Starting diagnostic script %s with configuration:\n%s",
                cfg['script'], yaml.safe_dump(cfg))

    # Create output directories
    output_directories = []
    if cfg['write_netcdf']:
        output_directories.append(cfg['work_dir'])
    if cfg['write_plots']:
        output_directories.append(cfg['plot_dir'])

    existing = [p for p in output_directories if os.path.exists(p)]

    if existing:
        if args.force:
            for output_directory in existing:
                logger.info("Removing %s", output_directory)
                shutil.rmtree(output_directory)
        elif not args.ignore_existing:
            logger.error(
                "Script will abort to prevent accidentally overwriting your "
                "data in these directories:\n%s\n"
                "Use -f or --force to force emptying the output directories "
                "or use -i or --ignore-existing to ignore existing output "
                "directories.", '\n'.join(existing))

    for output_directory in output_directories:
        logger.info("Creating %s", output_directory)
        if args.ignore_existing and os.path.exists(output_directory):
            continue
        os.makedirs(output_directory)

    yield cfg

    logger.info("End of diagnostic script run.")
