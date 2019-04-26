"""
netpyne_model_interpreter.py
Model interpreter for NWB. This class creates a geppetto type
"""
import base64
import logging
from io import BytesIO

import pygeppetto.model as pygeppetto
from PIL import Image as Img
from pygeppetto.model.model_factory import GeppettoModelFactory
from pygeppetto.model.values import Image
from pygeppetto.model.variables import Variable
from pygeppetto.services.model_interpreter import ModelInterpreter
from pygeppetto.utils import Singleton

from .nwb_reader import NWBReader
from .settings import *

from ..utils import guessUnits


class NWBModelInterpreter(ModelInterpreter, metaclass=Singleton):

    def __init__(self):
        self.factory = GeppettoModelFactory()
        self.nwb_reader = None

    @staticmethod
    def clean_name_to_variable(group_name):
        return ''.join(c for c in group_name.replace(' ', '_') if c.isalnum() or c in '_')

    def get_nwbfile(self):
        return self.nwb_reader.nwbfile

    def createModel(self, nwbfile_or_path, typeName='nwb', library='nwblib'):
        logging.debug(f'Creating a Geppetto Model from {nwbfile_or_path}')

        geppetto_model = self.factory.createGeppettoModel('GeppettoModel')
        nwb_geppetto_library = pygeppetto.GeppettoLibrary(name=library, id=library)
        geppetto_model.libraries.append(
            nwb_geppetto_library)  # FIXME the library should not be created here at every call

        nwbType = pygeppetto.CompositeType(id=typeName, name=typeName, abstract=False)
        # add top level variable
        nwb_file_variable = Variable(id='nwbfile')
        nwb_file_variable.types.append(nwbType)
        geppetto_model.variables.append(nwb_file_variable)
        # add top level type

        self.importType(nwbfile_or_path, nwbType, nwb_geppetto_library)
        return geppetto_model

    def importType(self, nwbfile_or_path, nwbType, nwb_geppetto_library, commonLibraryAccess=None):
        """
        Create the Geppetto Model for a nwb file.

        reates a group structure such as
        nwbfile.acquisition.[TIMESERIESNAME1]
        nwbfile.acquisition.[TIMESERIESNAME2]
        nwbfile.stimulus.[TIMESERIESNAME1]

        acquisition.[TIMESERIESNAME1].data
        acquisition.[TIMESERIESNAME1].time

        where each group entry contains the corresponding data from the nwb file.
        """




        nwb_geppetto_library.types.append(nwbType)



        # read data
        self.nwb_reader = NWBReader(nwbfile_or_path)

        time_series_list = self.nwb_reader.get_all_timeseries()



        for time_series in time_series_list:

            if not isinstance(time_series, SUPPORTED_TIME_SERIES_TYPES):
                logging.warning(f"Unsupported time series type: {type(time_series)}. Cannot import {time_series.name}")
                continue

            timeseries_path = self.nwb_reader.extract_time_series_path(time_series)

            current_variable_type = nwbType
            for path_element in timeseries_path:
                current_group_name = self.clean_name_to_variable(path_element)
                parent_type = current_variable_type

                # Me may already have added the current type previously
                current_variable_types = [variable.types[0] for variable in parent_type.variables if current_group_name == variable.name]
                if current_variable_types:
                    current_variable_type = current_variable_types[0]
                    continue


                current_variable_type = pygeppetto.CompositeType(id=current_group_name, name=current_group_name, abstract=False)
                nwb_geppetto_library.types.append(current_variable_type)

                current_variable = Variable(id=current_group_name, name=current_group_name,
                                            types=(current_variable_type,))

                parent_type.variables.append(current_variable)

            try:

                if isinstance(time_series, ImageSeries):
                    # TODO lazy fetching with importValue
                    plottable_image = NWBReader.get_timeseries_image_array(time_series)
                    md_time_series_variable = self.extract_image_variable('image', plottable_image)
                    current_variable_type.variables.append(self.factory.createStateVariable('image', md_time_series_variable))
                else:

                    # TODO we are temporarely creating one type for each timeseries
                    timeseries_type = self.get_timeseries_type(time_series.name)
                    nwb_geppetto_library.types.append(timeseries_type)
                    variable_name = self.clean_name_to_variable(time_series.name)
                    time_series_variable = Variable(id=variable_name, name=variable_name, types=(timeseries_type,))

                    current_variable_type.variables.append(time_series_variable)



            except ValueError as e:
                logging.error("Error loading timeseries: " + " -- ".join(e.args))
                import traceback
                traceback.print_exc()
            except NotImplementedError as e:
                logging.error("Unsupported feature: " + " -- ".join(e.args))
                import traceback
                traceback.print_exc()

    def get_timeseries_type(self, name="timeseries"):
        timeseries_type = pygeppetto.CompositeType(id=name, name="timeseries", abstract=False)
        timeseries_type.variables.append(
            self.factory.createStateVariable("time", self.factory.createImportValue()))  # TODO add unit to import
        timeseries_type.variables.append(self.factory.createStateVariable('data', self.factory.createImportValue()))
        return timeseries_type

    def importValue(self, import_value_path):
        path_pieces = import_value_path.split(path_separator)
        var_to_extract = path_pieces[-1]
        time_series = self.nwb_reader.retrieve_from_path(path_pieces[1:-1])
        # Geppetto timeseries does not include the time axe; we are using the last path piece to determine whether we
        # are looking for time or data

        if var_to_extract == 'time':
            timestamps = NWBReader.get_timeseries_timestamps(time_series, MAX_SAMPLES)
            timestamps_unit = guessUnits(time_series.timestamps_unit)
            return self.factory.createTimeSeries("time_" + time_series.name,
                                                 timestamps,
                                                 timestamps_unit)
        else:

            plottable_timeseries = NWBReader.get_plottable_timeseries(time_series, MAX_SAMPLES)

            unit = guessUnits(time_series.unit)
            time_series_value = self.factory.createTimeSeries("data_" + time_series.name,
                                                              plottable_timeseries[0],
                                                              unit)
            return time_series_value

    def import_value_from_path(self, import_value_path):
        path_pieces = import_value_path.split(path_separator)
        var_to_extract = path_pieces[-1]
        time_series = self.nwb_reader.retrieve_from_path(path_pieces[1:-1])
        # Geppetto timeseries does not include the time axe; we are using the last path piece to determine whether we
        # are looking for time or data

        if var_to_extract == 'time':
            timestamps = NWBReader.get_timeseries_timestamps(time_series, MAX_SAMPLES)
            timestamps_unit = guessUnits(time_series.timestamps_unit)
            return self.factory.createTimeSeries("time_" + time_series.name,
                                                 timestamps,
                                                 timestamps_unit)
        else:

            plottable_timeseries = NWBReader.get_plottable_timeseries(time_series, MAX_SAMPLES)

            unit = guessUnits(time_series.unit)
            time_series_value = self.factory.createTimeSeries("data_" + time_series.name,
                                                              plottable_timeseries[0],
                                                              unit)
            return time_series_value

    def extract_image_variable(self, metatype, plottable_timeseries):
        img = Img.fromarray(plottable_timeseries, 'RGB')
        data_bytes = BytesIO()
        img.save(data_bytes, 'PNG')
        data_str = base64.b64encode(data_bytes.getvalue()).decode('utf8')
        values = [Image(data=data_str)]
        md_time_series_variable = self.factory.createMDTimeSeries(metatype + "variable", values)
        return md_time_series_variable

    def getName(self):
        return "NWB Model Interpreter"

    def getDependentModels(self):
        return []