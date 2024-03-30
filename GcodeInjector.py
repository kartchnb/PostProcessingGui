# Copyright (c) 2023 Brad Kartchner
# The GcodeInjector is released under the terms of the LGPLv3 or higher.

import collections
import datetime
from functools import cached_property
from glob import glob
import json
import os.path
import re
from types import MethodType
from typing import Dict, Type, TYPE_CHECKING, List

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

from .RecursiveDictOverlay import recursiveDictOverlay

i18n_catalog = i18nCatalog('cura')



class GcodeInjector(QObject, Extension):
    ''' Extension-type plugin that provides a GUI interface for injecting 
        layer-based post-processing scripts '''

    def __init__(self, parent = None) -> None:
        ''' Basic class initialization only
            Most initialization is done in the _onMainWindowChanged function '''
        
        QObject.__init__(self, parent)
        Extension.__init__(self)

        self._injection_table:List[Dict] = []
        self._selected_injection_index:int = 0
        self._global_container_stack = None

        # Make scripts installed with this plugin visible to the post-processing plugin
        Resources.addSearchPath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Resources"))

        # Wait until the application is ready before completing initializing
        CuraApplication.getInstance().mainWindowChanged.connect(self._onMainWindowChanged)



    # All PyQt signals are here
    _active_injections_changed = pyqtSignal()
    _can_add_injections_changed = pyqtSignal()
    _injection_scripts_changed = pyqtSignal()
    _selected_injection_index_changed = pyqtSignal()
    _show_injection_panel_changed = pyqtSignal()
    


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
    def _simulationView(self):
        ''' Convenience property to cache and return the SimulationView object '''

        return Application.getInstance().getController().getView('SimulationView')



    @cached_property
    def _postProcessingPlugin(self):
        ''' Convenience property to cache and return the PostProcessingPlugin object '''

        plugin = PluginRegistry.getInstance().getPluginObject('PostProcessingPlugin')
        return plugin
    


    @cached_property
    def _injectionPanel(self)->QObject:
        ''' Convenience property to cache and return the injection panel '''

        qml_file_path = os.path.join(self._qmlDir, 'InjectionPanel.qml')
        component = CuraApplication.getInstance().createQmlComponent(qml_file_path, {'manager': self})
        return component
    


    @cached_property
    def _injectionMenu(self)->QObject:
        ''' Convenience property to cache and return the injection menu dialog '''

        qml_file_path = os.path.join(self._qmlDir, 'InjectionMenu.qml')
        component = CuraApplication.getInstance().createQmlComponent(qml_file_path, {'manager': self})
        return component
    


    """
    @property
    def injectionIndexes(self)->list:
        ''' Returns a list of the indexes of postprocessing scripts that correlate to injections '''
        
        indexes = []

        # Iterate over each active post-processing script
        for index in range(0, len(self._postProcessingPlugin._script_list)):

            # If this post-processing script is an injection script, record its index
            script = self._postProcessingPlugin._script_list[index]
            #layer_number_key = script.getSettingValueByKey('layer_number_key')
            #if layer_number_key is not None:
            #    indexes.append(index)   
            indexes.append(index)

        return indexes
    """



    """
    @pyqtProperty(bool, notify=_show_injection_panel_changed)
    def showInjectionPanel(self)->bool:
        ''' The injection panel is only shown when Cura is displaying the SimulationView '''
        
        try:
            state = CuraApplication.getInstance().getController().getActiveView().name == 'SimulationView'
        except AttributeError:
            state = False
        # TODO: Remove this line
        state = True
        return state
    """



    @pyqtProperty(bool, notify=_can_add_injections_changed)
    def canAddInjections(self)->bool:
        ''' Injections can only be added when Cura is displaying the SimulationView and the scene has been sliced '''

        try:
            state = CuraApplication.getInstance().getController().getActiveView().getActivity()
        except AttributeError:
            state = False
        return state


    """
    @pyqtProperty(list, notify=_injection_scripts_changed)
    def availableInjectionIds(self)->list[str]:
        ''' Return the ids of the available injection scripts (the JSON filename without the file extension)
            Post-Processing scripts are only supported if this plugin contains a matching overlay JSON file '''
        
        ids = list(self._injection_scripts.keys())
        return ids
    """



    @pyqtProperty(list, notify=_injection_scripts_changed)
    def availableInjectionsModel(self)->list[dict[str, str]]:
        ''' Return a model containing the names of all available injections '''

        model = [injection_dict['script_name'] for injection_dict in self._injection_table]
        
        return model



    def setSelectedInjectionIndex(self, index:int)->None:
        ''' Update the index of the selected injection script '''

        # Update the selected injection script index
        self._selected_injection_index = index

        # Update the saved plugin settings
        self._savePluginSettings()

        # Broadcast the index change
        self._selected_injection_index_changed.emit()




    @pyqtProperty(int, notify=_selected_injection_index_changed, fset=setSelectedInjectionIndex)
    def selectedInjectionIndex(self)->int:
        ''' Return the index of the currently-selected injection script '''

        return self._selected_injection_index



    @pyqtProperty(str, notify=_selected_injection_index_changed)
    def selectedDefinitionId(self)->str:
        ''' Return the ID of DefinitionContainer for the currently-selected injection script 
            This ID is the value of the "key" entry in the injection script's JSON overlay '''
        
        try:
            injection_dict = self._injection_table[self._selected_injection_index]
            id = injection_dict['script_key']
        except AttributeError:
            id = ''
        Logger.log('d', f'selectedDefinitionId = "{id}"')
        return id


    """
    @pyqtProperty(str, notify=_selected_injection_index_changed)
    def selectedStackId(self)->str:
        ''' Return the ID of the currently-selected script's ContainerStack for the currently-selected injection script
            This is a unique numerical ID based on the script object instance and is set by the Script class in PostProcessingPlugins '''
        
        try:
            script_id = self.availableInjectionIds[self._selected_injection_index]
            id = self._injection_scripts[script_id].getStackId()
        except AttributeError:
            id = ''
        return id
    """


    @pyqtProperty(list, notify=_active_injections_changed)
    def activeInjectionsModel(self)->list:
        ''' Return a list of dictionaries describing the layer number and script name of each active injection '''

        active_injections_model = []

        # Iterate over each active post-processing script
        for index in range(0, len(self._postProcessingPlugin._script_list)):

            # Retrieve the postprocessing script
            script = self._postProcessingPlugin._script_list[index]
            script_key = script.getSettingData()['key']

            for injection_dict in self._injection_table:

                overlay_script_key = injection_dict['script_key']
                
                if overlay_script_key == script_key:

                    # Iterate over the critical settings for the injection
                    critical_settings_dict = injection_dict['critical_settings']
                    critical_settings_match = True
                    for critical_setting_key, critical_setting_value in critical_settings_dict.items():

                        # If the critical setting is not correct, ignore this script
                        try:
                            setting_value = script.getSettingValueByKey(critical_setting_key)
                            if setting_value != critical_setting_value:
                                critical_settings_match = False
                                break
                        except KeyError as e:
                            critical_settings_match = False
                            break

                    if critical_settings_match == False:
                        continue

                    # Look up the layer number setting in the script
                    layer_number_key = injection_dict['layer_number_key']
                    layer_number = script.getSettingValueByKey(layer_number_key)

                    # Retrieve the script name
                    script_name = injection_dict['script_name']

                    # Add the script information to the active injections model
                    active_injections_model.append({'script_name': script_name, 'layer_number': layer_number})

        # Sort the injections by ascending layer number
        active_injections_model = sorted(active_injections_model, key=lambda x: x['layer_number'])

        return active_injections_model



    @pyqtSlot()
    def onInsertInjectionButtonLeftClicked(self)->None:
        ''' When the injection menu button is left-clicked, an injection is inserted at the active layer '''

        self._injectionMenu.show()   



    @pyqtSlot()
    def onInsertInjectionButtonRightClicked(self)->None:
        ''' When the injection menu button is right-clicked, the injection settings menu is shown '''

        layer_number = self._simulationView.getCurrentLayer() + 1 # Add one to match Cura's layer numbering
        self._injectionMenu.show()
        self._addInjection(layer_number)



    @pyqtSlot(int)
    def onExistingInjectionButtonLeftClicked(self, layer_number:int)->None:
        ''' When an injection button is left-clicked, the associated layer is selected in the SimulationView '''

        self._simulationView.setLayer(layer_number - 1) # Subtract one because of how Cura numbers its layers in the GUI



    @pyqtSlot(int)
    def onExistingInjectionButtonRightClicked(self, layer_number:int)->None:
        ''' When an injection button is right-clicked, the injection is deleted '''

        self._removeInjection(layer_number)



    """
    @pyqtSlot()
    def updatePostProcessingScripts(self) -> None:
        self.saveInjectionScriptSettings()
    """



    def _onActivityChanged(self)->None:
        ''' Called when the sliced state of the SimulationView has changed or the view has changed
            If the scene has been sliced, the activity is True, otherwise False '''
        
        # The injection panel may need to be hidden or displayed based on this activity change
        self._show_injection_panel_changed.emit()
        self._can_add_injections_changed.emit()
        self._active_injections_changed.emit()



    def _onGlobalContainerStackChanged(self) -> None:
        '''When the global container stack is changed, swap out the list of active scripts.'''

        # Disconnect from the previous global container stack
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.disconnect(self._loadPluginSettings)

        # Remember the new global container stack and listen for it to change
        self._global_container_stack = Application.getInstance().getGlobalContainerStack()
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.connect(self._loadPluginSettings)
            self._global_container_stack.propertyChanged.connect(self._onGlobalContainerStackPropertyChanged)

        # Restore or initialize the injection scripts based on the new global container stack
        self._loadPluginSettings()



    def _onMainWindowChanged(self)->None:
        ''' The application should be ready at this point so most plugin initialization is done here '''

        # We won't be needing this callback anymore (it's probably not necessary to disconnect, but I'm doing it anyway)
        CuraApplication.getInstance().mainWindowChanged.disconnect(self._onMainWindowChanged)

        # Load overlay data
        self._loadInjectionOverlays()

        # Remember the current global container stack        
        self._global_container_stack = Application.getInstance().getGlobalContainerStack()
        
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.connect(self._loadPluginSettings)
            self._global_container_stack.propertyChanged.connect(self._onGlobalContainerStackPropertyChanged)

        # Monitor for changes to the simulation view and active view
        self._simulationView.activityChanged.connect(self._onActivityChanged)
        CuraApplication.getInstance().getController().activeViewChanged.connect(self._onActivityChanged)

        # Create the injection panel
        CuraApplication.getInstance().addAdditionalComponent('saveButton', self._injectionPanel)

        # Run a callback when a write is started
        Application.getInstance().getOutputDeviceManager().writeStarted.connect(self._onWriteStarted)

        # Listen for post-processing script changes
        self._postProcessingPlugin.scriptListChanged.connect(self._onPostProcessingScriptListChanged)
        self._postProcessingPlugin._onPropertyChanged.connect(self._onPostProcessingPropertyChanged)



    def _onGlobalContainerStackPropertyChanged(self, instance:SettingInstance, property:str)->None:
        ''' Called whenever a property is changed in the global container stack '''
        
        # TODO: Is there a way to react only to PostProcessingPlugin property changes?
        # Look into the SettingInstance class
        if property == 'value':
            
            # Update the active injections list to force the panel to update
            self._active_injections_changed.emit()



    def _onPostProcessingScriptListChanged(self)->None:
        ''' Called whenever the post-processing scripts change '''

        # Update the active injections
        self._active_injections_changed.emit()



    def _onWriteStarted(self, output_device)->None:
        ''' Called whenver gcode is being written out to an output device or file '''

        # Convert the list of layer numbers to a dictionary so it can be searched easily
        injected_layers_dict = {x['layer_number']: x['script_name'] for x in self.activeInjectionsModel}

        # If there are no injections, there is nothing to be processed
        if len(injected_layers_dict) == 0:
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

            if layer_number in injected_layers_dict.keys():

                # Calculate elapsed times
                section_elapsed_time = elapsed_time - layer_start_time
                total_elapsed_time += section_elapsed_time
                layer_start_time = elapsed_time

                # Grab the script name
                script_name = injected_layers_dict[layer_number]

                # Compile a time string
                decomposed_time_string = self._secondsToDecomposedTimeString(section_elapsed_time)
                clock_time_string = self._secondsToClockTimeString(total_elapsed_time)
                time_string = f'{decomposed_time_string} (about {clock_time_string})'
                message_lines.append(f'- {script_name} after {time_string}')

        # Assemble the message        
        message = '\n'.join(message_lines)
        message = 'The following scripts will be activated:\n' + message
        Message(message, lifetime=0, title="Gcode Injector").show()



    def _enumerateLayerElapsedTime(self, gcode):
        ''' Iterates over the lines in the gcode that is passed in and returns the elapsed time for each layer '''

        # Keep track of the current layer number
        layer_number = 0

        # The regex to use when searching for new layers
        layer_regex = re.compile(r';LAYER:(\d+)\s*')

        # The regex to use when searching for layer elapsed times
        elapsed_time_regex = re.compile(r';TIME_ELAPSED:(\d+\.?\d*)')

        # Iterate over each "clump" of gcode
        for clump in gcode:

            # Split the layer into lines
            lines = clump.split('\n')

            # Iterate over each line in the layer
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
        ''' Converts a seconds value to a string containing hours, minutes, and seconds '''

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
        ''' Converts a seconds value to clock time from now '''

        now = datetime.datetime.now()
        complete = now + datetime.timedelta(seconds=seconds)
        complete_string = complete.strftime('%-I:%M %p')
        if now.date() != complete.date():
            date_string = complete.strftime('%-d %b')
            complete_string += f' on {date_string}'

        return complete_string
    


    """
    def _addInjection(self, layer_number:int)->None:
        ''' Add an injection at the given layer based on the currently-selected injection script '''

        # Create a new post-processing script based on the currently-selected injection master script
        selected_injection_id = self.availableInjectionIds[self._selected_injection_index]
        injection_script = self._injection_scripts[selected_injection_id]
        new_script = type(injection_script)()
        new_script.initialize()

        # Hack - Don't reslice after script changes because that will mess up the preview display
        new_script._stack.propertyChanged.disconnect(new_script._onPropertyChanged)

        # Hack - Mark this script as an injection by adding a 'layer_number_key' setting to its DefinitionContainer
        injectionDefinitionContainer = injection_script._stack.getBottom()
        try:
            keyDefinition = injectionDefinitionContainer.findDefinitions(key='layer_number_key')[0]
        except IndexError:
            Logger.log('e', 'The injection script is missing a "layer_number_key" entry')
            return
        new_script._stack.getBottom().addDefinition(keyDefinition)

        # Transfer settings from the script master
        instanceContainer = copy.deepcopy(injection_script._stack.getTop())
        new_script._stack.replaceContainer(0, instanceContainer)
        
        # Set the layer number for this post-processing script
        layer_number_key = new_script.getSettingValueByKey('layer_number_key')
        new_script._stack.getTop().setProperty(layer_number_key, 'value', layer_number)

        # Iterate over each active post-processing script
        for index in range(0, len(self._postProcessingPlugin._script_list)):

            # If this post-processing script is an injection for the same layer being injected to, replace it
            script = self._postProcessingPlugin._script_list[index]
            layer_number_key = script.getSettingValueByKey('layer_number_key')
            if layer_number_key is not None:
                script_layer_number = script.getSettingValueByKey(layer_number_key)
                if script_layer_number == layer_number:
                    self._postProcessingPlugin._script_list[index] = new_script
                    break            

        # If there is no injection at this layer, add one
        else:
            self._postProcessingPlugin._script_list.append(new_script)
            self._postProcessingPlugin.setSelectedScriptIndex(len(self._postProcessingPlugin._script_list) - 1)

        self._postProcessingPlugin.scriptListChanged.emit()
        self._active_injections_changed.emit()
    """



    def _removeInjection(self, selected_layer_number:int)->None:
        ''' Remove an injection from the list of active post-processing scripts in the PostProcessingPlugin '''

        # Iterate over each active post-processing script
        for index in range(0, len(self._postProcessingPlugin._script_list)):

            # Retrieve the postprocessing script
            script = self._postProcessingPlugin._script_list[index]
            script_key = script.getSettingData()['key']

            try:
                overlay = self._injection_table[script_key]
            except KeyError:
                continue

            # Look up the layer number
            layer_number_key = overlay['layer_number_key']
            layer_number = script.getSettingValueByKey(layer_number_key)

            if selected_layer_number == layer_number:
                # Remove the injection script from the list of active post-processing scripts
                self._postProcessingPlugin._script_list.pop(index)
                if len(self._postProcessingPlugin._script_list) - 1 < self._postProcessingPlugin._selected_script_index:
                    self._postProcessingPlugin._selected_script_index = len(self._postProcessingPlugin._script_list) - 1
                # TODO: Is this line redundant?
                self._postProcessingPlugin.scriptListChanged.emit()
                self._postProcessingPlugin.selectedIndexChanged.emit()  # Ensure that settings are updated
                # TODO: Is this line redundant?
                self._active_injections_changed.emit()

        self._postProcessingPlugin.scriptListChanged.emit()
        self._active_injections_changed.emit()


    def _savePluginSettings(self) -> None:
        ''' Save the plugin settings to the global container stack '''

        if self._global_container_stack is not None:
            pass
            #self._saveToGlobalContainerStack('selected_injection_index', self._selected_injection_index)
        else:
            Logger.log('e', 'Unable to save injection scripts without a global container stack')



    def _loadPluginSettings(self)->None:
        ''' Restore or initialize injection scripts and their settings '''

        selected_injection_name = None

        # Restore the previously-selected injection ID
        if self._global_container_stack is not None:
            pass
        else:
            Logger.log('e', 'Unable to restore plugin settings because there is no global container stack')
            return



    def _saveToGlobalContainerStack(self, metadata_entry:str, setting:str)->None:
        ''' Save the requested setting to the global container stack without triggering a change event '''

        # We don't want this write to trigger a metadata changed event
        self._global_container_stack.metaDataChanged.disconnect(self._loadPluginSettings)
        self._postProcessingPlugin._global_container_stack.metaDataChanged.disconnect(self._postProcessingPlugin._restoreScriptInforFromMetadata)

        # Initialize the metadata entry if it's not already present
        if metadata_entry not in self._global_container_stack.getMetaData():
            self._global_container_stack.setMetaDataEntry(metadata_entry, '')

        # Save the setting
        self._global_container_stack.setMetaDataEntry(metadata_entry, setting)

        # Continue listening for metadata changes
        self._global_container_stack.metaDataChanged.connect(self._loadPluginSettings)
        self._postProcessingPlugin._global_container_stack.metaDataChanged.connect(self._postProcessingPlugin._restoreScriptInforFromMetadata)



    def _loadInjectionOverlays(self)->None:
        ''' Load all overlays files '''

        self._injection_table:List[Dict] = []

        # Retrieve the names of all .json files included with the plugin
        json_dir = os.path.join(self._pluginDir, 'Resources', 'Json')
        json_wildcard = os.path.join(json_dir, '*.json')
        json_file_paths = glob(json_wildcard)

        # Iterate over each available JSON overlay file
        for json_file_path in json_file_paths:

            # Grab just the file name of this overlay file
            overlay_file_name = os.path.basename(json_file_path)

            # Open the overlay
            with open(json_file_path, 'r') as json_file:

                try:
                    # Read in the contents as a dictionary
                    overlay_dict = json.load(json_file, object_pairs_hook=collections.OrderedDict)

                    # Determine the key of the corresponding post-processing script
                    overlay_script_key = overlay_dict['script_key']

                    # Look up the matching post-processing script
                    try:
                        # Determine the matching post-processing script class
                        script_class = self._postProcessingPlugin._loaded_scripts[overlay_script_key]
                        overlay_dict['script_class'] = script_class
                    except KeyError:
                        Logger.log('w', f'The script key "{overlay_script_key}" in "{overlay_file_name}" does not match any available post-processing scripts')
                        continue

                    try:
                        # Use a temporary instantation to grab script information
                        temp_script = script_class()
                        script_name = temp_script.getSettingData()['name']
                        overlay_dict['script_name'] = script_name
                    except KeyError:
                        Logger.log('e', f'The post-processing script with key "{overlay_script_key}" does not have a "name" entry')
                        continue

                    # Record the injection information in the injection table
                    self._injection_table.append(overlay_dict)

                except json.decoder.JSONDecodeError as e:
                    Logger.log('w', f'Overlay file "{overlay_file_name}" is malformed:\n{e}')

                except KeyError:
                    Logger.log('w', f'Overlay file "{overlay_file_name}" is missing a "script_key" definition and will be ignored')
