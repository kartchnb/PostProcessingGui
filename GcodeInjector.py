# Copyright (c) 2018 Jaime van Kessel, Ultimaker B.V.
# The PostProcessingPlugin is released under the terms of the LGPLv3 or higher.

import collections
import configparser  # The script lists are stored in metadata as serialised config files.
import copy
from functools import cached_property
from glob import glob
import importlib.util
import io  # To allow configparser to write to a string.
import json
import os.path
import pkgutil
import sys
from types import MethodType
from typing import Dict, Type, TYPE_CHECKING, List, Optional, cast

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot
PYQT_VERSION = 6

from UM.Application import Application
from UM.Extension import Extension
from UM.Logger import Logger
from UM.Message import Message
from UM.PluginRegistry import PluginRegistry
from UM.Resources import Resources
from UM.Settings.ContainerFormatError import ContainerFormatError
from UM.Settings.ContainerRegistry import ContainerRegistry
from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.SettingDefinition import DefinitionPropertyType
from UM.Settings.SettingDefinition import SettingDefinition
from UM.Trust import Trust, TrustBasics
from UM.i18n import i18nCatalog
from cura import ApplicationMetadata
from cura.CuraApplication import CuraApplication

from .RecursiveDictOverlay import recursiveDictOverlay

i18n_catalog = i18nCatalog('cura')

if TYPE_CHECKING:
    from .Script import Script


class GcodeInjector(QObject, Extension):
    '''Extension type plugin that enables pre-written scripts to post process g-code files.'''

    # The identifier used to locate this plugin's saved data in the global container stack metadata
    _plugin_metadata_id:str = 'gcode_injection_settings'



    def __init__(self, parent = None) -> None:
        ''' Basic initialization only
            Most initialization is done in the _onMainWindowChanged function '''
        
        QObject.__init__(self, parent)
        Extension.__init__(self)

        self._show_injection_panel:bool = False
        self._injection_scripts:Dict[str, Type(Script)] = {} # Dict[script name, script class]
        self._selected_injection_index:int = 0

        self._global_container_stack = None

        # Wait until the application is ready before completing initializing
        CuraApplication.getInstance().mainWindowChanged.connect(self._onMainWindowChanged)



    # All PyQt signals are here
    _can_add_injections = pyqtSignal()
    _injection_scripts_changed = pyqtSignal()
    _selected_injection_index_changed = pyqtSignal()
    _active_injections_changed = pyqtSignal()
    


    @cached_property
    def _jsonDir(self)->str:
        ''' Convenience property to cache and return the JSON directory '''

        json_dir = os.path.join(self.pluginDir, 'Resources', 'Json')
        return json_dir
    


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

        return PluginRegistry.getInstance().getPluginObject('PostProcessingPlugin')
    


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
    


    @cached_property
    def _availableJsonFileNames(self):
        ''' Return a list of all the JSON overlay files included with this plugin '''

        json_dir = os.path.join(self._pluginDir, 'Resources', 'Json')
        json_wildcard = os.path.join(json_dir, '*.json')
        json_fileNames = glob(json_wildcard)
        return json_fileNames
    


    @cached_property
    def _availableJsonOverlays(self):
        ''' Return a list of the JSON overlay IDs included with this plugin
            These IDs are just the JSON filename stripped of the extension '''
        
        json_ids = [os.path.splitext(os.path.basename(fileName))[0] for fileName in self._availableJsonFileNames]
        return json_ids



    @pyqtProperty(bool, notify=_can_add_injections)
    def canAddInjections(self)->bool:
        ''' Injections can only be added when on the SimulationView with a sliced model '''
        
        try:
            state = CuraApplication.getInstance().getController().getActiveView().getActivity()
        except AttributeError:
            state = False
        return state



    @pyqtProperty(list, notify=_injection_scripts_changed)
    def availableInjectionNames(self)->list[str]:
        ''' Return the names of the available injection scripts
            Post-Processing scripts are only supported if this plugin contains a matching overlay JSON file '''
        
        names = list(self._injection_scripts.keys())
        return names
    


    @pyqtProperty(list, notify=_injection_scripts_changed)
    def availableInjectionModel(self)->list[dict[str, str]]:
        ''' Return a model used to provide the injection menu with the injection names '''

        model = [{'name': name} for name in self.availableInjectionNames]
        return model
    


    def setSelectedInjectionIndex(self, index:int)->None:
        ''' Update the index of the selected injection script '''

        # Update the master script
        self._selected_injection_index = index
        self._selected_injection_index_changed.emit()



    @pyqtProperty(int, notify=_selected_injection_index_changed, fset=setSelectedInjectionIndex)
    def selectedInjectionIndex(self)->int:
        ''' Return the index of the currently-selected injection script '''

        return self._selected_injection_index
    


    @pyqtProperty(str, notify=_selected_injection_index_changed)
    def selectedInjectionName(self)->str:
        ''' Return the name of the selected injection '''

        try:
            name = self.availableInjectionNames[self._selected_injection_index]
        except IndexError:
            name = ''

        return name



    @pyqtProperty(str, notify=_selected_injection_index_changed)
    def selectedDefinitionId(self)->str:
        ''' Return the ID of DefinitionContainer for the currently-selected injection script 
            This ID is the value of the "key" entry in the injection script's JSON overlay '''
        
        try:
            script_name = self.availableInjectionNames[self._selected_injection_index]
            id = self._injection_scripts[script_name].getDefinitionId()
        except AttributeError:
            id = ''
        return id
    


    @pyqtProperty(str, notify=_selected_injection_index_changed)
    def selectedStackId(self)->str:
        ''' Return the ID of the currently-selected script's ContainerStack for the currently-selected injection script
            This is a unique numerical ID based on the script object instance and is set by the Script class in PostProcessingPlugins '''
        
        try:
            script_name = self.availableInjectionNames[self._selected_injection_index]
            id = self._injection_scripts[script_name].getStackId()
        except AttributeError:
            id = ''
        return id
    


    @pyqtProperty(list, notify=_active_injections_changed)
    def injectionModel(self)->list:
        ''' Return a list of layer numbers that have injections '''

        layer_model = []
        
        # Iterate over each active post-processing script
        for script in self._postProcessingPlugin._script_list:
            
            self._log(f'script = "{script}"')
            # Determine the key that is associated with the layer number
            layer_number_key = script.getSettingValueByKey('layer_number_key')

            self._log(f'layer_number_key = "{layer_number_key}"')
            # This script is an injection only if it has a 'layer_number_key' setting
            if layer_number_key is not None:
                
                # Record the injection layer number
                layer_number = script.getSettingValueByKey(layer_number_key)
                self._log(f'layer_number = "{layer_number}"')
                layer_model.append({'layer_number': layer_number, 'script_name': script.getSettingData()['name']})

        # Sort the entries by layer number
        sorted_layer_model = sorted(layer_model, key=lambda x: x['layer_number'])

        nums = [str(d['layer_number']) for d in sorted_layer_model]
        num_str = ', '.join(nums)
        self._log(f'identified injection layers: [{num_str}]')

        return sorted_layer_model



    @pyqtSlot()
    def onInsertInjectionButtonLeftClicked(self)->None:
        ''' When the injection menu button is left-clicked, an injection is inserted at the active layer '''

        layer_number = self._simulationView.getCurrentLayer() + 1 # Add one to match Cura's layer numbering
        self._addInjection(layer_number)



    @pyqtSlot()
    def onInsertInjectionButtonRightClicked(self)->None:
        ''' When the injection menu button is right-clicked, the injection settings menu is shown '''

        self._injectionMenu.show()   



    @pyqtSlot(int)
    def onExistingInjectionButtonLeftClicked(self, layer_number:int)->None:
        ''' When an injection button is left-clicked, the associated layer is selected in the SimulationView '''

        self._simulationView.setLayer(layer_number - 1) # Subtract one because of how Cura numbers its layers in the GUI



    @pyqtSlot(int)
    def onExistingInjectionButtonRightClicked(self, layer_number:int)->None:
        ''' When an injection button is right-clicked, the injection is deleted '''

        Message(f'onExistingInjectionButtonRightClicked called for layer {layer_number}').show()
        self._removeInjection(layer_number)



    def _addInjection(self, layer_number:int)->None:
        ''' Add an injection at the given layer based on the currently-selected injection script '''

        self._log(f'_addInjection for layer {layer_number}')
        # Create a new post-processing script based on the currently-selected injection script
        selected_injection_name = self.availableInjectionNames[self._selected_injection_index]
        injection_script = self._injection_scripts[selected_injection_name]
        new_script = type(injection_script)()
        new_script.initialize()

        # Hack - Don't reslice after script changes because that will mess up the preview display
        new_script._stack.propertyChanged.disconnect(new_script._onPropertyChanged)

        # Transfer settings from the script master
        instanceContainer = copy.deepcopy(injection_script._stack.getTop())
        new_script._stack.replaceContainer(0, instanceContainer)

        # Hack - Mark this script as an injection by adding a 'layer_number_key' setting to its DefinitionContainer
        definitionContainer = injection_script._stack.getBottom()
        definition = definitionContainer.findDefinitions(key='layer_number_key')[0]
        new_script._stack.getBottom().addDefinition(definition)
        
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

                    Message(f'Replaced the injection at layer {layer_number} with "{selected_injection_name}"')
                    break            

        # If there is no injection at this layer, add one
        else:
            self._postProcessingPlugin._script_list.append(new_script)
            self._postProcessingPlugin.setSelectedScriptIndex(len(self._postProcessingPlugin._script_list) - 1)

            Message(f'Added an injection at layer {layer_number} for "{selected_injection_name}"')

            # Notify the PostProcessingPlugin to update itself      
            self._postProcessingPlugin.scriptListChanged.emit()



    def _removeInjection(self, layer_number:int)->None:
        ''' Remove an injection from the list of active post-processing scripts in the PostProcessingPlugin '''

        self._log(f'_removeInjection for layer {layer_number}')
        # Iterate over each active post-processing script
        for index in range(0, len(self._postProcessingPlugin._script_list)):

            # Only look into this script if it is an injection script (meaning, it has a 'layer_number_key' setting)
            script = self._postProcessingPlugin._script_list[index]
            layer_number_key = script.getSettingValueByKey('layer_number_key')
            if layer_number_key is not None:

                # Check if this injection is for the given layer number
                injected_layer_number = script.getSettingValueByKey(layer_number_key)
                if injected_layer_number == layer_number:

                    # Remove the injection script from the list of active post-processing scripts
                    self._postProcessingPlugin._script_list.pop(index)
                    if len(self._postProcessingPlugin._script_list) - 1 < self._postProcessingPlugin._selected_script_index:
                        self._postProcessingPlugin._selected_script_index = len(self._postProcessingPlugin._script_list) - 1
                    self._postProcessingPlugin.scriptListChanged.emit()
                    self._postProcessingPlugin.selectedIndexChanged.emit()  # Ensure that settings are updated
                    self._active_injections_changed.emit()

                    # There's no need to search any further
                    return



    def _onActivityChanged(self)->None:
        ''' Called when the sliced state of the SimulationView has changed or the view has changed
            If the scene has been sliced, the activity is True, otherwise False '''
        
        # The injection panel may need to be hidden or displayed based on this activity change
        self._can_add_injections.emit()



    def _onMainWindowChanged(self)->None:
        ''' The application should be ready at this point so most plugin initialization is done here '''

        self._log('_onMainWindowChanged')
        # We won't be needing this callback anymore (it's probably not necessary to disconnect)
        CuraApplication.getInstance().mainWindowChanged.disconnect(self._onMainWindowChanged)

        # Remember the current global container stack        
        self._global_container_stack = Application.getInstance().getGlobalContainerStack()
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.connect(self._restoreInjectionScripts)

        # Connect to the simulation view
        self._simulationView.activityChanged.connect(self._onActivityChanged)
        CuraApplication.getInstance().getController().activeViewChanged.connect(self._onActivityChanged)

        # Restore or initialize the injection scripts
        self._restoreInjectionScripts()

        # Listen for changes to the active post-processing scripts
        #self._postProcessingPlugin.scriptListChanged.connect(self._onActivePostProcessingScriptsChanged)
        self._postProcessingPlugin.scriptListChanged.connect(self._active_injections_changed)

        # Make sure the injection panel gets updated for the first time
        self._active_injections_changed.emit()
        self._postProcessingPlugin.scriptListChanged.emit()

        # Add the injection panel to Cura's UI
        CuraApplication.getInstance().addAdditionalComponent('saveButton', self._injectionPanel)



    def _onActivePostProcessingScriptsChanged(self)->None:
        ''' Called when post-processing scripts are added, removed, or rearranged by the PostProcessingPlugin '''

        self._log('_onActivePostProcessingScriptsChanged')
        # This may or may not involve injections, so we'll need to update just in case
        self._active_injections_changed.emit()



    def _restoreInjectionScripts(self)->None:
        ''' Restore or initialize injection scripts and their settings '''

        self._log('restoreInjectionScripts')
        selected_injection_name = None

        # Start by loading all available injections with default settings
        self._initializeInjectionScripts()

        # If the injections are not saved in the global container stack, then stick with the default settings
        self._global_container_stack
        if self._global_container_stack is None or not self._global_container_stack.getMetaDataEntry(self._plugin_metadata_id):
            return

        # Grab the combined injection settings string from the global container stack
        combined_settings_string = self._global_container_stack.getMetaDataEntry(self._plugin_metadata_id)

        # Iterate over each injection script settings string within the combined settings string
        for injection_settings_string in combined_settings_string.split('\n'):
            if not injection_settings_string:
                continue

            # Reverse the escape characters introduced when saving
            injection_settings_string = injection_settings_string.replace(r'\\\n', '\n').replace(r'\\\\', '\\\\')

            # Feed the injection settings to the ConfigParser
            parser = configparser.ConfigParser(interpolation=None)
            parser.optionxform = str # Don't transform the setting keys as they are case-sensitive.
            try:
                parser.read_string(injection_settings_string)
            except configparser.Error as e:
                Logger.error('Stored injection settings have syntax errors: {err}'.format(err = str(e)))
                return
    
            # Iterate over each script in the parser information
            # Although there should only be one, the parser contains a DEFAULT section that is not used
            for injection_name, injection_settings in parser.items():  # There should only be one, really! Otherwise we can't guarantee the order or allow multiple uses of the same script.
                
                # Ignore the DEFAULT config section
                if injection_name == 'DEFAULT':
                    continue

                # Handle the Plugin Settings section specially
                if injection_name == 'Plugin Settings':
                    plugin_settings = injection_settings

                    # Handle recognized plugin settings
                    try:
                        selected_injection_name = plugin_settings['selected_injection_name']
                    except KeyError:
                        pass

                # Only include recognized injections
                elif injection_name in self._injection_scripts:
                    # Restore each of the saved settings for this injection script
                    for setting_key, setting_value in injection_settings.items():
                        self._injection_scripts[injection_name]._instance.setProperty(setting_key, 'value', setting_value)

                # Report unrecognized "scripts"
                else:
                    Logger.log('e', f'Unknown post-processing script "{injection_name}" was encountered in this global stack.')
                    continue

            # Determine the selected injection index
            try:
                self.setSelectedInjectionIndex(self.availableInjectionNames.index(selected_injection_name))
            except ValueError:
                self.setSelectedInjectionIndex(0)

        self._active_injections_changed.emit()



    @pyqtSlot()
    def saveInjectionScripts(self) -> None:
        ''' Save injection scripts and settings to the global container stack '''

        self._log('saveInjectionScripts')
        # Can't do anything if there's no global container stack to write to
        if self._global_container_stack is None:
            return
        
        settings_list: List[str] = []

        # Create a dictionary for plugin settings that need to be saved
        settings_dict = {}
        settings_dict ['Plugin Settings'] = {
            'selected_injection_name': self.availableInjectionNames[self._selected_injection_index]
        }

        # Combine the plugin settings with the injection scripts settings into one dictionary
        settings_dict.update(self._injection_scripts)

        # Iterate over each injection script
        for injection_name, injection_script in settings_dict.items():
            
            # Encode the injection script and its settings using ConfigParser
            parser = configparser.ConfigParser(interpolation=None)  # We'll encode the script as a config with one section. The section header is the key and its values are the settings.
            parser.optionxform = str  # type: ignore # Don't transform the setting keys as they are case-sensitive.

            # Add a section for this injection script
            parser.add_section(injection_name)

            try:
                # Add each injection script setting
                for key in injection_script.getSettingData()['settings']:
                    value = injection_script.getSettingValueByKey(key)
                    parser[injection_name][key] = str(value)
    
            except AttributeError:
                # If this occurs, it means this is probably a plugin setting that needs to be handled differently
                section_name = injection_name
                plugin_settings_dict = injection_script
                
                # Iterate over each plugin setting name and value
                for setting_name, setting_value in plugin_settings_dict.items():
                    parser[section_name] [setting_name] = setting_value

            # Read the parser into a single string
            serialized = io.StringIO()  # ConfigParser can only write to streams. Fine.
            parser.write(serialized)
            serialized.seek(0)
            settings = serialized.read()

            # Escape strings that will cause issues
            settings = settings.replace('\\\\', r'\\\\').replace('\n', r'\\\n')  # Escape newlines because configparser sees those as section delimiters.
            
            # Add this injection script's settings to the list
            settings_list.append(settings)

        # Combine all injection script setting strings into a single string
        injection_settings_string = '\n'.join(settings_list)  # ConfigParser should never output three newlines in a row when serialised, so it's a safe delimiter.

        # We don't want this write to trigger a metadata changed event
        self._global_container_stack.metaDataChanged.disconnect(self._restoreInjectionScripts)
        self._postProcessingPlugin._global_container_stack.metaDataChanged.disconnect(self._postProcessingPlugin._restoreScriptInforFromMetadata)

        # Initialize the metadata entry if it's not already present
        if self._plugin_metadata_id not in self._global_container_stack.getMetaData():
            self._global_container_stack.setMetaDataEntry(self._plugin_metadata_id, '')

        # Save the injections scripts settings to metadata
        self._global_container_stack.setMetaDataEntry(self._plugin_metadata_id, injection_settings_string)

        self._log(f'Saved "{injection_settings_string}"')
        # Continue listening for metadata changes
        self._global_container_stack.metaDataChanged.connect(self._restoreInjectionScripts)
        self._postProcessingPlugin._global_container_stack.metaDataChanged.connect(self._postProcessingPlugin._restoreScriptInforFromMetadata)



    def _onGlobalContainerStackChanged(self) -> None:
        '''When the global container stack is changed, swap out the list of active scripts.'''

        # Disconnect from the previous global container stack
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.disconnect(self._restoreInjectionScripts)

        # Remember the new global container stack and listen for it to change
        self._global_container_stack = Application.getInstance().getGlobalContainerStack()
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.connect(self._restoreInjectionScripts)

        # Restore or initialize the injection scripts based on the new global container stack
        self._restoreInjectionScripts()



    def _initializeInjectionScripts(self)->None:
        ''' Initializes all valid injection scripts with default values '''

        # Iterate over each script in the post-processing plugin
        for script_name in self._postProcessingPlugin._loaded_scripts.keys():

            # Only initialize scripts with matching JSON overlays
            if script_name in self._availableJsonOverlays:
                self._injection_scripts[script_name] = self._loadInjectionScript(script_name)

        # Select the first injection by default
        self._selected_injection_index = 0



    def _loadInjectionScript(self, injection_name)->None:
        ''' Load a single injection script by script name '''
        
        # Create the injection script
        new_script = self._postProcessingPlugin._loaded_scripts[injection_name]()
        
        # Load the settings overlay for the script
        json_fileName = f'{injection_name}.json'
        json_path = os.path.join(self._pluginDir, 'Resources', 'Json', json_fileName)
        with open(json_path, 'r') as json_file:
            overlay_setting_data = json.load(json_file, object_pairs_hook = collections.OrderedDict)

        # Overlay the JSON settings onto the script's original settings
        setting_data = recursiveDictOverlay(new_script.getSettingData(), overlay_setting_data)

        # Hack to override the script's settings with the overlaid settings
        new_script.getSettingData = MethodType(lambda self: setting_data, new_script)

        # Initialize the script now
        new_script.initialize()

        # Hack - Don't reslice after script changes because that will mess up the preview display
        new_script._stack.propertyChanged.disconnect(new_script._onPropertyChanged)

        return new_script



    # Todo: Delete this function and remove all trace
    def _log(self, message):
        Message(message).show()
        Logger.log('d', message)
