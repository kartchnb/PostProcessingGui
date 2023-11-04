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



    def __init__(self, parent = None) -> None:
        ''' Basic initialization only
            Most initialization is done in the _onMainWindowChanged function '''
        
        QObject.__init__(self, parent)
        Extension.__init__(self)

        self._show_injection_panel = False
        self._available_injection_scripts:Dict[str, Type(Script)] = []
        self._selected_injection_index = 0
        self._injection_script_master = None
        self._injections = {}

        self._global_container_stack = Application.getInstance().getGlobalContainerStack()
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.connect(self._restoreScriptInfoFromMetadata)

        # Wait until the application is ready before completing initializing
        CuraApplication.getInstance().mainWindowChanged.connect(self._onMainWindowChanged)



    # All QT signals are here
    _can_add_injections_changed = pyqtSignal()
    _loaded_script_list_changed = pyqtSignal()
    _injection_script_master_changed = pyqtSignal()
    _injections_changed = pyqtSignal()

    

    @cached_property
    def _qmlDir(self)->str:
        ''' Convenience property to cache and return the directory of QML files '''

        plugin_dir = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
        qml_dir = os.path.join(plugin_dir, 'Resources', 'QML', f'QT{PYQT_VERSION}')
        return qml_dir
    


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
    def _simulationView(self):
        ''' Convenience property to cache and return the SimulationView object '''

        return Application.getInstance().getController().getView('SimulationView')


    @cached_property
    def _postProcessingPlugin(self):
        ''' Convenience property to cache and return the PostProcessingPlugin object '''

        return PluginRegistry.getInstance().getPluginObject('PostProcessingPlugin')
    


    @cached_property
    def _availableJsonFileNames(self):
        ''' Return a list of all the JSON overlay files included with this plugin '''

        plugin_dir = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
        json_dir = os.path.join(plugin_dir, 'Resources', 'Json')
        json_wildcard = os.path.join(json_dir, '*.json')
        json_fileNames = glob(json_wildcard)
        return json_fileNames
    


    @cached_property
    def _availableJsonIds(self):
        ''' Return a list of the JSON overlay IDs included with this plugin
            These IDs are just the JSON filename stripped of the extension '''
        
        json_ids = [os.path.splitext(os.path.basename(fileName))[0] for fileName in self._availableJsonFileNames]
        return json_ids



    @pyqtProperty(bool, notify=_can_add_injections_changed)
    def canAddInjections(self)->bool:
        try:
            state = CuraApplication.getInstance().getController().getActiveView().getActivity()
        except AttributeError:
            state = False
        return state
            
    @canAddInjections.setter
    def canAddInjections(self, value:bool)->None:
        self._show_injection_panel = value
        self._can_add_injections_changed.emit()



    @pyqtProperty(list, notify=_loaded_script_list_changed)
    def availableInjectionKeys(self)->list:
        ''' Return the keys of the supported post-processing scripts
            Scripts are only supported if this plugin contains a matching overlay JSON file '''
        
        keys = [key for key in self._postProcessingPlugin.loadedScriptList if key in self._availableJsonIds]
        return keys



    @pyqtProperty(list, notify=_loaded_script_list_changed)
    def availableInjectionLabels(self)->list:
        ''' Return the labels of the supported post-processing scripts '''

        labels = [{'name': self._postProcessingPlugin.getScriptLabelByKey(key)} for key in self.availableInjectionKeys]
        return labels
    


    def setSelectedInjectionIndex(self, index:int)->None:
        ''' Create a new master script to use for injections '''

        # Create the injection script
        selected_script_key = self.availableInjectionKeys[index]
        new_script = self._postProcessingPlugin._loaded_scripts[selected_script_key]()
        
        # Load the settings overlay for the script
        json_fileName = self._availableJsonFileNames[index]
        with open(json_fileName, 'r') as json_file:
            overlay_setting_data = json.load(json_file, object_pairs_hook = collections.OrderedDict)

        # Overlay the settings onto the script's original settings
        setting_data = recursiveDictOverlay(new_script.getSettingData(), overlay_setting_data)

        # Hack override the script's settings with the overlaid settings
        new_script.getSettingData = MethodType(lambda self: setting_data, new_script)

        # Initialze the script now
        new_script.initialize()

        # Hack - Don't reslice after script changes because that will mess up the preview display
        new_script._stack.propertyChanged.disconnect(new_script._onPropertyChanged)

        # Update the master script
        self._selected_injection_index = index
        self._injection_script_master = new_script

        self._injection_script_master_changed.emit()



    @pyqtProperty(int, notify=_injection_script_master_changed, fset=setSelectedInjectionIndex)
    def selectedInjectionIndex(self)->int:
        ''' Return the index of the currently-selected master script '''

        return self._selected_injection_index



    @pyqtProperty(str, notify=_injection_script_master_changed)
    def selectedDefinitionId(self)->str:
        ''' Return the ID of the currently-selected DefinitionContainer 
            This ID is the value of the "key" entry in the script's settings '''
        
        try:
            id = self._injection_script_master.getDefinitionId()
        except AttributeError:
            id = ''
        return id
    


    @pyqtProperty(str, notify=_injection_script_master_changed)
    def selectedStackId(self)->str:
        ''' Return the ID of the currently-selected script's ContainerStack
            This is a unique numerical ID based on the script object instance '''
        
        try:
            id = self._injection_script_master.getStackId()
        except AttributeError:
            id = ''
        return id
    


    @pyqtProperty(list, notify=_injections_changed)
    def injectedLayerNumbers(self)->list:
        layer_numbers = []
        for script in self._postProcessingPlugin._script_list:
            layer_number_key = script.getSettingValueByKey('layer_number_key')
            if layer_number_key is not None:
                layer_number = script.getSettingValueByKey(layer_number_key)
                layer_numbers.append({'layer_number': layer_number, 'script_name': script.getSettingData()['name']})
        return layer_numbers



    @pyqtSlot()
    def onInsertInjectionButtonLeftClicked(self)->None:
        layer_number = self._simulationView.getCurrentLayer()
        self._addInjection(layer_number)



    @pyqtSlot()
    def onInsertInjectionButtonRightClicked(self)->None:
        self._injectionMenu.show()   



    @pyqtSlot(int)
    def onExistingInjectionButtonLeftClicked(self, layer_number:int)->None:
        self._simulationView.setLayer(layer_number)



    @pyqtSlot(int)
    def onExistingInjectionButtonRightClicked(self, layer_number:int)->None:
        self._removeInjection(layer_number)



    def _addInjection(self, layer_number:int)->None:
        # Create a new script with the same type as the script master
        new_script = type(self._injection_script_master)()
        new_script.initialize()

        # Hack - Don't reslice after script changes because that will mess up the preview display
        new_script._stack.propertyChanged.disconnect(new_script._onPropertyChanged)

        # Transfer settings from the script master
        instanceContainer = copy.deepcopy(self._injection_script_master._stack.getTop())
        new_script._stack.replaceContainer(0, instanceContainer)

        # Hack - Mark this script as an injection
        definitionContainer = self._injection_script_master._stack.getBottom()
        definitions = definitionContainer.findDefinitions(key='layer_number_key')
        definition = definitions[0]
        new_script._stack.getBottom().addDefinition(definition)
        
        # Set the layer number for this post-processing script
        layer_number_key = new_script.getSettingValueByKey('layer_number_key')
        new_script._stack.getTop().setProperty(layer_number_key, 'value', layer_number)

        for index in range(0, len(self._postProcessingPlugin._script_list)):
            script = self._postProcessingPlugin._script_list[index]
            layer_number_key = script.getSettingValueByKey('layer_number_key')
            if layer_number_key is not None:
                script_layer_number = script.getSettingValueByKey(layer_number_key)
                if script_layer_number == layer_number:
                    self._postProcessingPlugin._script_list[index] = new_script
                    break            
        else:
            self._postProcessingPlugin._script_list.append(new_script)
            self._postProcessingPlugin.setSelectedScriptIndex(len(self._postProcessingPlugin._script_list) - 1)

        # Add the post-processing script to the PostProcessingPlugin's script list        
        self._postProcessingPlugin.scriptListChanged.emit()



    def _removeInjection(self, layer_number:int)->None:
        for index in range(0, len(self._postProcessingPlugin._script_list)):
            script = self._postProcessingPlugin._script_list[index]
            layer_number_key = script.getSettingValueByKey('layer_number_key')
            if layer_number_key is not None:
                script_layer_number = script.getSettingValueByKey(layer_number_key)
                if script_layer_number == layer_number:
                    del(self._postProcessingPlugin._script_list[index])
                    self._postProcessingPlugin.scriptListChanged.emit()
                    return



    def _onActivityChanged(self)->None:
        ''' Called when the sliced state of the SimulationView has changed or the view has changed
            If the scene has been sliced, the activity is True, otherwise False '''
        
        self._can_add_injections_changed.emit()



    def _onMainWindowChanged(self)->None:
        ''' The application should be ready at this point '''

        # Don't need this callback anymore
        CuraApplication.getInstance().mainWindowChanged.disconnect(self._onMainWindowChanged)

        # Initialize the script master
        self.setSelectedInjectionIndex(self._selected_injection_index)

        # Connect to the simulation view
        self._simulationView.activityChanged.connect(self._onActivityChanged)
        Application.getInstance().getController().activeViewChanged.connect(self._onActivityChanged)

        # Create the injection panel
        CuraApplication.getInstance().addAdditionalComponent('saveButton', self._injectionPanel)
        self._injections_changed.emit()

        # Listen for changes to the post-processing scripts
        self._postProcessingPlugin.loadedScriptListChanged.connect(self._loaded_script_list_changed)
        self._postProcessingPlugin.scriptListChanged.connect(self._onPostProcessingScriptsChanged)

        self._global_container_stack = Application.getInstance().getGlobalContainerStack()
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.connect(self._restoreScriptInfoFromMetadata)
        self._restoreScriptInfoFromMetadata()

        self._injections_changed.emit()



    def _onPostProcessingScriptsChanged(self)->None:
        self._injections_changed.emit()



    def _restoreScriptInfoFromMetadata(self)->None:
        Message('Restoring settings from metadata').show()
        Logger.log('d', 'Restoring settings from metadata')
        new_stack = self._global_container_stack
        if new_stack is None:
            Logger.log('d', 'new_stack is None')
            Logger.log('d', f'But Application.getInstance().getGlobalContainerStack() = {Application.getInstance().getGlobalContainerStack()}')
            return

        settings = new_stack.getMetaDataEntry('gcode_injection_settings')
        try:
            settings = settings.replace(r'\\\n', '\n').replace(r'\\\\', '\\\\')  # Unescape escape sequences.
        except Exception as e:
            Logger.log('e', f'Exception = {e}')
            raise
        Logger.log('d', f'settings = {settings}')
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str  # type: ignore  # Don't transform the setting keys as they are case-sensitive.
        try:
            parser.read_string(settings)
        except configparser.Error as e:
            Logger.error('Stored GcodeInjector settings have syntax errors: {err}'.format(err = str(e)))
            return
    
        for script_name, settings in parser.items():  # There should only be one, really! Otherwise we can't guarantee the order or allow multiple uses of the same script.
            if script_name == 'DEFAULT':  # ConfigParser always has a DEFAULT section, but we don't fill it. Ignore this one.
                continue
            if script_name not in self._availableJsonIds:  # Don't know this post-processing plug-in.
                Logger.log('e',
                            'Unknown post-processing script {script_name} was encountered in this global stack.'.format(
                                script_name=script_name))
                continue
            new_script = self._postProcessingPlugin._loaded_scripts[script_name]()
            new_script.initialize()
            for setting_key, setting_value in settings.items():  # Put all setting values into the script.
                if new_script._instance is not None:
                    new_script._instance.setProperty(setting_key, 'value', setting_value)

            index = self.availableInjectionKeys.index(script_name)
            self.setSelectedInjectionIndex(index)
            self._selected_injection_index = index
            self._injection_script_master = new_script

            self._injection_script_master_changed.emit()



    @pyqtSlot()
    def writeSettingsToStack(self) -> None:
        Message('Writing settings to stack').show()
        parser = configparser.ConfigParser(interpolation = None)  # We'll encode the script as a config with one section. The section header is the key and its values are the settings.
        parser.optionxform = str  # type: ignore # Don't transform the setting keys as they are case-sensitive.
        script_name = self._injection_script_master.getSettingData()['key']
        parser.add_section(script_name)
        for key in self._injection_script_master.getSettingData()['settings']:
            value = self._injection_script_master.getSettingValueByKey(key)
            Logger.log('d', f'Writing to parser: "{key}" = "{value}"')
            parser[script_name][key] = str(value)
        serialized = io.StringIO()  # ConfigParser can only write to streams. Fine.
        parser.write(serialized)
        serialized.seek(0)
        settings = serialized.read()
        Logger.log('d', 'read settings')
        settings = settings.replace('\\\\', r'\\\\').replace('\n', r'\\\n')  # Escape newlines because configparser sees those as section delimiters.

        Logger.log('d', f'settings = "{settings}"')

        if self._global_container_stack is None:
            return

        # Ensure we don't get triggered by our own write.
        self._global_container_stack.metaDataChanged.disconnect(self._restoreScriptInfoFromMetadata)

        if 'gcode_injection_settings' not in self._global_container_stack.getMetaData():
            self._global_container_stack.setMetaDataEntry('gcode_injection_settings', '')

        self._global_container_stack.setMetaDataEntry('gcode_injection_settings', settings)

        # We do want to listen to other events.
        self._global_container_stack.metaDataChanged.connect(self._restoreScriptInfoFromMetadata)



    def _onGlobalContainerStackChanged(self) -> None:
        '''When the global container stack is changed, swap out the list of active scripts.'''
        Message('Global Container stack changed').show()
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.disconnect(self._restoreScriptInfoFromMetadata)

        self._global_container_stack = Application.getInstance().getGlobalContainerStack()

        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.connect(self._restoreScriptInfoFromMetadata)
        self._restoreScriptInfoFromMetadata()



    def _onPostProcessingScriptsPropertyChanged(self)->None:
        self._injections_changed.emit()
