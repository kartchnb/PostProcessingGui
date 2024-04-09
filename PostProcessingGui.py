# Copyright (c) 2024 Brad Kartchner
# Released under the terms of the LGPLv3 or higher.

import collections
import datetime
from functools import cached_property
from glob import glob
import json
import os.path
import re
from typing import Dict, TYPE_CHECKING, List

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot
PYQT_VERSION = 6

from UM.Application import Application
from UM.Extension import Extension
from UM.Logger import Logger
from UM.Message import Message
from UM.PluginRegistry import PluginRegistry
from UM.Resources import Resources
from UM.Settings.SettingInstance import SettingInstance #For typing.
from UM.i18n import i18nCatalog
from cura.CuraApplication import CuraApplication

i18n_catalog = i18nCatalog('cura')



class PostProcessingGui(QObject, Extension):
    ''' Extension-type plugin that provides a GUI interface for adding 
        layer-based post-processing scripts '''

    def __init__(self, parent = None) -> None:
        ''' Basic class initialization only
            Most initialization is done in the _onMainWindowChanged function '''
        
        QObject.__init__(self, parent)
        Extension.__init__(self)

        # Contains information about each post-processing script supported by
        # this plugin
        self._script_table:List[Dict] = []

        # Keeps track of the currently-selected post-processing script
        self._selected_script_index:int = 0

        # Holds the post-processing script that is waiting to be added
        self._tempScript = None

        # Keeps track of the global container stack
        self._global_container_stack = None        
        
        # Make scripts installed with this plugin visible to the post-processing plugin
        Resources.addSearchPath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Resources"))

        # Wait until the application is ready before completing initializing
        CuraApplication.getInstance().mainWindowChanged.connect(self._onMainWindowChanged)



    # All PyQt signals are here
    _available_scripts_model_changed = pyqtSignal()
    _active_scripts_model_changed = pyqtSignal()
    _show_add_scripts_button_changed = pyqtSignal()
    _selected_script_index_changed = pyqtSignal()
    _show_active_scripts_panel_changed = pyqtSignal()
    


    @cached_property
    def _metaDataId(self)->str:
        ''' Defines the ID used to identify this plugin's data '''

        return self.getPluginId().lower()



    @cached_property
    def _pluginDir(self)->str:
        ''' Convenience property to cache and return the plugin directory '''
    
        plugin_dir = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
        return plugin_dir

    

    @cached_property
    def _qmlDir(self)->str:
        ''' Convenience property to cache and return the directory of QML files '''

        qml_dir = os.path.join(self._pluginDir, 'Resources', 'QML', f'QT{PYQT_VERSION}')
        return qml_dir
    


    @cached_property
    def _activeScriptsPanel(self)->QObject:
        ''' Convenience property to cache and return the active scripts panel '''

        qml_file_path = os.path.join(self._qmlDir, 'ActiveScriptsPanel.qml')
        component = CuraApplication.getInstance().createQmlComponent(qml_file_path, {'manager': self})
        return component
    


    @cached_property
    def _addScriptMenu(self)->QObject:
        ''' Convenience property to cache and return the add script menu '''

        qml_file_path = os.path.join(self._qmlDir, 'AddScriptMenu.qml')
        component = CuraApplication.getInstance().createQmlComponent(qml_file_path, {'manager': self})
        return component



    @property
    def _postProcessingPlugin(self):
        ''' Convenience property to return the PostProcessingPlugin object '''

        plugin = PluginRegistry.getInstance().getPluginObject('PostProcessingPlugin')
        return plugin
        


    @pyqtProperty(bool, notify=_show_active_scripts_panel_changed)
    def showActiveScriptsPanel(self)->bool:
        ''' Determines when the active scripts panel is displayed '''

        # For now, the active scripts panel is always shown, although the script
        # buttons themselves are only enabled when previewing a sliced model
        return True



    @pyqtProperty(bool, notify=_show_add_scripts_button_changed)
    def showAddScriptButton(self)->bool:
        ''' Scripts can only be added through the GUI when previewing a sliced
            model '''

        try:
            # If the simulation view is active, then the getActivity method can
            # be used to determine if the model has been sliced
            # The add script button is only shown if the model has been sliced
            state = CuraApplication.getInstance().getController().getActiveView().getActivity()
        except AttributeError:
            # If the simulation view is not active, then the add script button
            # is not shown
            state = False
        return state



    @pyqtProperty(list, notify=_available_scripts_model_changed)
    def availableScriptsModel(self)->list[dict[str, str]]:
        ''' Return a model containing the names of all active scripts supported
            by this plugin '''

        model = [{'script_name': script_data['script_name']} for script_data in self._script_table]
        
        return model



    def setSelectedScriptIndex(self, index:int)->None:
        ''' Update the index of the selected script '''

        # Update the selected script index
        self._selected_script_index = index

        # Create a temporary script
        script_data = self._script_table[self._selected_script_index]
        script_class = script_data['script_class']
        self._tempScript = script_class()
        self._tempScript.initialize()

        # Changes to this script shouldn't force reslicing
        self._tempScript._stack.propertyChanged.disconnect(self._tempScript._onPropertyChanged)

        # Update the critical settings of the script
        critical_settings = script_data['critical_settings']
        for critical_setting, critical_value in critical_settings.items():
            self._tempScript._stack.getTop().setProperty(critical_setting, 'value', critical_value)

        # Set the layer number in the script
        layer_number_setting = script_data['layer_number_setting']   
        layer_number = Application.getInstance().getController().getView('SimulationView').getCurrentLayer() + 1
        self._tempScript._stack.getTop().setProperty(layer_number_setting, 'value', layer_number)
            
        # Broadcast that the selected script has been changed
        self._selected_script_index_changed.emit()



    @pyqtProperty(int, notify=_selected_script_index_changed, fset=setSelectedScriptIndex)
    def selectedScriptIndex(self)->int:
        ''' Return the index of the currently-selected post-processing script '''

        return self._selected_script_index



    @pyqtProperty(str, notify=_selected_script_index_changed)
    def selectedDefinitionId(self)->str:
        ''' Return the ID of DefinitionContainer for the currently-selected 
            script '''
        
        try:
            id = self._tempScript.getDefinitionId()
        except AttributeError:
            id = ''
        return id



    @pyqtProperty(str, notify=_selected_script_index_changed)
    def selectedStackId(self)->str:
        ''' Return the ID of the currently-selected script's ContainerStack 
            This is a unique numerical ID based on the script object instance 
            and is set by the Script class '''

        try:
            id = self._tempScript.getStackId()
        except AttributeError:
            id = ''
        return id



    @pyqtProperty(list, notify=_active_scripts_model_changed)
    def activeScriptsModel(self)->list:
        ''' Return a list of dictionaries describing the name and layer number
            for each active script supported by this plugin '''

        active_scripts_model = []

        # Iterate over each active post-processing script
        for index in range(0, len(self._postProcessingPlugin._script_list)):

            # Retrieve the postprocessing script
            script = self._postProcessingPlugin._script_list[index]
            script_key = script.getSettingData()['key']

            # Iterate over each supported script
            for script_data in self._script_table:

                # Process this post-processing script if it's supported
                if script_data['script_key'] == script_key:
                    
                    try:
                        # Iterate over the critical settings for the script
                        critical_settings_match = True
                        critical_settings_dict = script_data['critical_settings']
                        for critical_setting_key, critical_setting_value in critical_settings_dict.items():

                            # Check for missing or mismatched critical settings
                            try:
                                setting_value = script.getSettingValueByKey(critical_setting_key)
                                if setting_value != critical_setting_value:
                                    critical_settings_match = False
                                    break

                            except KeyError as e:
                                critical_settings_match = False
                                break

                        # If there is a critical setting mismatch, ignore this 
                        # script
                        if critical_settings_match == False:
                            continue

                    except KeyError:
                        # No critical_settings for this script?  Fine
                        pass

                    # Look up the layer number setting in the script
                    layer_number_setting = script_data['layer_number_setting']
                    try:
                        layer_number = int(script.getSettingValueByKey(layer_number_setting))
                    except ValueError:
                        # If the layer number cannot be interpreted as an 
                        # integer, then the script can't be used
                        continue

                    # Retrieve the script name, key, and stackId
                    script_name = script_data['script_name']
                    script_key = script_data['script_key']

                    # Add the script information to the  model
                    active_scripts_model.append({'script_key': script_key, 'script_name': script_name, 'layer_number': layer_number, 'script_index': index})

        # Sort the scripts by ascending layer number
        active_scripts_model = sorted(active_scripts_model, key=lambda x: x['layer_number'])
        return active_scripts_model



    @pyqtSlot()
    def addScript(self)->None:
        ''' Add the selected script into the list of post-processing scripts '''

        # Now that the script is being added, changes should cause reslicing
        self._tempScript._stack.propertyChanged.connect(self._tempScript._onPropertyChanged)

        # Add the script to the active post-processing scripts
        self._postProcessingPlugin._script_list.append(self._tempScript)
        self._postProcessingPlugin.setSelectedScriptIndex(len(self._postProcessingPlugin._script_list) - 1)
        self._postProcessingPlugin.scriptListChanged.emit()
        self._postProcessingPlugin._propertyChanged()

        # Trigger the post-processing plugin to update itself
        self._postProcessingPlugin.writeScriptsToStack()

        # "Set" the selected script index to generate a new temporary script
        self.setSelectedScriptIndex(self._selected_script_index)



    @pyqtSlot()
    def onAddScriptButtonLeftClicked(self)->None:
        ''' When the add script button is left-clicked, the add script menu is
            shown '''

        # Update the layer number in the selected script
        script_data = self._script_table[self._selected_script_index]
        layer_number_setting = script_data['layer_number_setting'] 
        layer_number = Application.getInstance().getController().getView('SimulationView').getCurrentLayer() + 1
        self._tempScript._stack.getTop().setProperty(layer_number_setting, 'value', layer_number)

        # Display the add script menu
        self._addScriptMenu.show()   



    @pyqtSlot()
    def onAddScriptButtonRightClicked(self)->None:
        ''' For now, nothing happens when the add script button is right-
            clicked '''
        pass



    @pyqtSlot(int)
    def onActiveScriptButtonLeftClicked(self, layer_number:int)->None:
        ''' When an active script button is left-clicked, the associated layer 
            is selected in the SimulationView '''

        # Subtract one from the layer due to the way Cura numbers its layers in 
        # the GUI
        Application.getInstance().getController().getView('SimulationView').setLayer(layer_number - 1)



    @pyqtSlot(int)
    def onActiveScriptButtonCenterClicked(self, script_index:int)->None:
        ''' When an active script button is center-clicked, the script for that
            button is removed from the list of post-processing scripts '''

        self._removeScript(script_index)



    @pyqtSlot(int)
    def onActiveScriptButtonRightClicked(self, script_index:int)->None:
        ''' When an active script button is right-clicked, the post-processing
            menu is displayed '''

        self._postProcessingPlugin.setSelectedScriptIndex(script_index)
        self._postProcessingPlugin.showPopup()



    @pyqtSlot()
    def savePluginSettings(self) -> None:
        ''' Save the plugin settings to the global container stack '''

        if self._global_container_stack is not None:

            # Get the currently-selected script key
            script_data = self._script_table[self._selected_script_index]
            selected_script_key = script_data['script_key']

            # Don't bother the post-processing plugin with this write
            self._postProcessingPlugin._global_container_stack.metaDataChanged.disconnect(self._postProcessingPlugin._restoreScriptInforFromMetadata)

            # Initialize the plugin's metadata entry if it's not already present
            if self._metaDataId not in self._global_container_stack.getMetaData():
                self._global_container_stack.setMetaDataEntry(self._metaDataId, '')

            # Save the selected script key
            # TODO: Should probably save a serialized dict of settings for future expandibility
            self._global_container_stack.setMetaDataEntry(self._metaDataId, selected_script_key)

            # Don't bother the post-processing plugin with this write
            self._postProcessingPlugin._global_container_stack.metaDataChanged.connect(self._postProcessingPlugin._restoreScriptInforFromMetadata)

        else:
            Logger.log('e', 'Unable to save plugin settings without a global container stack')



    def _onActivityChanged(self)->None:
        ''' Called when the sliced state of the SimulationView has changed or 
            the view has changed
            If the scene has been sliced, the activity is True, otherwise it is
            False '''
        
        # Broadcast the change to the GUI elements
        self._show_active_scripts_panel_changed.emit()
        self._show_add_scripts_button_changed.emit()



    def _onGlobalContainerStackChanged(self) -> None:
        '''When the global container stack is changed, swap out the list of 
           active scripts.'''

        # Disconnect from the previous global container stack
        try:
            self._global_container_stack.propertyChanged.disconnect(self._onGlobalContainerStackPropertyChanged)
        except TypeError as e:
            Logger.log('e', f'Error disconnecting from old Global Container Stack: {e}')

        # Remember the new global container stack and listen for it to change
        self._global_container_stack = Application.getInstance().getGlobalContainerStack()
        try:
            self._global_container_stack.propertyChanged.connect(self._onGlobalContainerStackPropertyChanged)
        except TypeError as e:
            Logger.log('e', f'Error connecting to old Global Container Stack: {e}')

        # Restore or initialize the available scripts based on the new global container stack
        self._loadPluginSettings()



    def _onMainWindowChanged(self)->None:
        ''' The application should be ready at this point so most plugin 
            initialization is done here '''

        # We won't be needing this callback anymore 
        # (it's probably not necessary to disconnect, but I'm doing it anyway)
        CuraApplication.getInstance().mainWindowChanged.disconnect(self._onMainWindowChanged)

        # Remember the current global container stack        
        self._global_container_stack = Application.getInstance().getGlobalContainerStack()
        
        # Connect to global container stack events
        try:
            self._global_container_stack.propertyChanged.connect(self._onGlobalContainerStackPropertyChanged)
        except TypeError as e:
            Logger.log('e', f'Error connecting to the Global Container Stack: {e}')

        # Initialize the scripts
        self._initializeScriptTable()

        # Monitor for changes to the simulation view and active view
        Application.getInstance().getController().getView('SimulationView').activityChanged.connect(self._onActivityChanged)
        CuraApplication.getInstance().getController().activeViewChanged.connect(self._onActivityChanged)

        # Create the active scripts panel
        CuraApplication.getInstance().addAdditionalComponent('saveButton', self._activeScriptsPanel)

        # Listen for a gcode write to start
        Application.getInstance().getOutputDeviceManager().writeStarted.connect(self._onWriteStarted)

        # Listen for post-processing script changes
        self._postProcessingPlugin.scriptListChanged.connect(self._onPostProcessingScriptListChanged)

        # Load persistant plugin settings
        self._loadPluginSettings()



    def _onGlobalContainerStackPropertyChanged(self, instance:SettingInstance, property:str)->None:
        ''' Called whenever a property is changed in the global container stack '''
        
        # Only react to value changes
        if property == 'value':
            
            # Update the active scripts panel
            self._active_scripts_model_changed.emit()



    def _onPostProcessingScriptListChanged(self)->None:
        ''' Called whenever the active post-processing scripts change '''

        # Update the active scripts
        self._active_scripts_model_changed.emit()



    def _onWriteStarted(self, output_device)->None:
        ''' Called whenver gcode is being written out to an output device or 
            file 
            This is used to provide an estimatin of when the layer for the 
            script will be reached during the print process'''

        # Convert the list of layer numbers to a dictionary so it can be searched easily
        active_scripts_data = {entry['layer_number']: entry['script_name'] for entry in self.activeScriptsModel}

        # If there are no active scripts, there is nothing to be processed
        if len(active_scripts_data) == 0:
            return         
                
        # Retrieve the g-code
        scene = Application.getInstance().getController().getScene()

        try:
            # Proceed if the g-code is valid
            gcode_dict = getattr(scene, 'gcode_dict')
        except AttributeError:
            # If there is no g-code, there's nothing more to do
            return

        try:
            # Retrieve the g-code for the current build plate
            active_build_plate_id = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
            gcode = gcode_dict[active_build_plate_id]
        except (TypeError, KeyError):
            # If there is no g-code for the current build plate, there's nothing more to do
            return
        
        # Keep track of the total elapsed time
        layer_start_time = 0.0
        total_elapsed_time = 0.0

        message_lines = []

        # Iterate over each layer in the gcode
        for layer_number, elapsed_time in self._enumerateLayerElapsedTime(gcode):

            if layer_number in active_scripts_data.keys():

                # Calculate elapsed times
                section_elapsed_time = elapsed_time - layer_start_time
                total_elapsed_time += section_elapsed_time
                layer_start_time = elapsed_time

                # Grab the script name
                script_name = active_scripts_data[layer_number]

                # Compile a time string
                decomposed_time_string = self._secondsToDecomposedTimeString(section_elapsed_time)
                clock_time_string = self._secondsToClockTimeString(total_elapsed_time)
                time_string = f'{decomposed_time_string} (about {clock_time_string})'
                message_lines.append(f'- "{script_name}" after {time_string}')

        # Assemble and display the message        
        message = '\n'.join(message_lines)
        message = 'The following scripts will be activated:\n' + message
        Message(message, lifetime=0, title=self.getPluginId()).show()



    def _enumerateLayerElapsedTime(self, gcode):
        ''' Iterates over the lines in the gcode that is passed in and returns 
            the elapsed time for each layer '''

        # Keep track of the current layer number
        layer_number = 0

        # The regex to use when searching for new layers
        layer_regex = re.compile(r';LAYER:(\d+)\s*')

        # The regex to use when searching for layer elapsed times
        elapsed_time_regex = re.compile(r';TIME_ELAPSED:(\d+\.?\d*)')

        # Iterate over each "clump" of gcode
        for clump in gcode:

            # Iterate over each line in the clump
            lines = clump.split('\n')
            for line in lines:

                # Check if this line marks the start of a new layer in the gcode
                match = re.match(layer_regex, line)
                if match:

                    # Extract the layer number
                    layer_number = int(match.group(1))

                    # The layer number needs to be incremented by 1 to match Cura's layer numbers
                    layer_number += 1

                # Check if this line contains the elapsed time for the current layer
                match = re.match(elapsed_time_regex, line)
                if match:

                    # Extract the elapsed time
                    elapsed_time = float(match.group(1))

                    # Yield the values for this line
                    yield layer_number, elapsed_time



    def _secondsToDecomposedTimeString(self, seconds)->str:
        ''' Converts a number of seconds to a string containing hours, minutes, 
            and seconds '''

        hours = int(seconds / 3600)
        seconds -= hours * 3600
        minutes = int(seconds/60)
        seconds -= minutes * 60

        if hours > 0:
            decomposed_string = f'{hours} hours and {minutes} minutes'
        elif minutes > 1:
            decomposed_string = f'{minutes} minutes'
        elif minutes > 0:
            decomposed_string = f'{minutes} minute and {seconds} seconds'
        else:
            decomposed_string = f'{seconds} seconds'

        return  decomposed_string
    


    def _secondsToClockTimeString(self, seconds)->str:
        ''' Converts a number of seconds to estimated clock time '''

        now = datetime.datetime.now()
        complete = now + datetime.timedelta(seconds=seconds)
        complete_string = complete.strftime('%-I:%M %p')
        if now.date() != complete.date():
            date_string = complete.strftime('%-d %b')
            complete_string += f' on {date_string}'

        return complete_string



    def _removeScript(self, script_index:int)->None:
        ''' Remove a script from the list of active post-processing scripts 
            in the PostProcessingPlugin '''

        self._postProcessingPlugin._script_list.pop(script_index)
        if len(self._postProcessingPlugin._script_list) - 1 < self._postProcessingPlugin._selected_script_index:
            self._postProcessingPlugin._selected_script_index = len(self._postProcessingPlugin._script_list) - 1
        self._postProcessingPlugin.scriptListChanged.emit()
        self._postProcessingPlugin.selectedIndexChanged.emit()  # Ensure that settings are updated

        self._postProcessingPlugin.writeScriptsToStack()



    def _loadPluginSettings(self)->None:
        ''' Restore this plugin's settings '''

        # Restore the previously-selected script
        if self._global_container_stack is not None:
            
            # Load the saved script key
            selected_script_key = self._global_container_stack.getMetaDataEntry(self._metaDataId)

            # Find the index of the script with the matching key
            selected_script_index = 0
            for index in range(0, len(self._script_table)):
                script_data = self._script_table[index]
                script_key = script_data['script_key']
                if script_key == selected_script_key:
                    selected_script_index = index
                    break

            # Update the selected script index
            self.setSelectedScriptIndex(selected_script_index)

        else:
            Logger.log('e', 'Unable to restore plugin settings because there is no global container stack')



    def _initializeScriptTable(self)->None:
        ''' Get information for all post-processing scripts supported by this
            plugin '''

        self._script_table:List[Dict] = []

        # Retrieve the names of all .json files included with the plugin
        json_dir = os.path.join(self._pluginDir, 'Resources', 'Json')
        json_wildcard = os.path.join(json_dir, '*.json')
        json_file_paths = glob(json_wildcard)

        # Iterate over each available JSON file
        for json_file_path in json_file_paths:

            # Grab just the file name of this jsob file
            json_file_name = os.path.basename(json_file_path)

            # Open the json file
            with open(json_file_path, 'r') as json_file:

                try:
                    # Read in the contents as a dictionary
                    json_dict = json.load(json_file, object_pairs_hook=collections.OrderedDict)

                    # Determine the key of the corresponding post-processing script
                    json_script_key = json_dict['script_key']

                    # Look up the matching post-processing script
                    try:
                        # Determine the matching post-processing script class
                        script_class = self._postProcessingPlugin._loaded_scripts[json_script_key]
                        json_dict['script_class'] = script_class
                    except KeyError:
                        Logger.log('w', f'The script key "{json_script_key}" in "{json_file_name}" does not match any available post-processing scripts')
                        continue

                    try:
                        # Use a temporary instantation to grab script information
                        temp_script = script_class()
                        script_name = temp_script.getSettingData()['name']
                        json_dict['script_name'] = script_name
                    except KeyError:
                        continue

                    # Record the script information in the table
                    self._script_table.append(json_dict)

                except json.decoder.JSONDecodeError as e:
                    Logger.log('w', f'JSON file "{json_file_name}" is malformed:\n{e}')

                except KeyError:
                    Logger.log('w', f'JSON file "{json_file_name}" is missing a "script_key" definition and will be ignored')

        # Sort the script table by name
        self._script_table = sorted(self._script_table, key=lambda x: x['script_name'])
