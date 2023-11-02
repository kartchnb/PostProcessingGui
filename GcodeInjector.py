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

i18n_catalog = i18nCatalog("cura")

if TYPE_CHECKING:
    from .Script import Script


class GcodeInjector(QObject, Extension):
    """Extension type plugin that enables pre-written scripts to post process g-code files."""



    def __init__(self, parent = None) -> None:
        ''' Basic initialization only
            Most initialization is done in the _onMainWindowChanged function '''
        
        QObject.__init__(self, parent)
        Extension.__init__(self)

        self._show_injection_panel = False
        self._selected_injection_index = 0
        self._injection_script_master = None
        self._injections = {}

        # Wait until the application is ready before completing initializing
        CuraApplication.getInstance().mainWindowChanged.connect(self._onMainWindowChanged)

        # Intercept gcode before it is sent to its destination
        Application.getInstance().getOutputDeviceManager().writeStarted.connect(self.onWriteStarted)



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



    def onWriteStarted(self, output_device)->None:
        Message('Write Started').show()



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
        Logger.log('d', f'setting_data = {setting_data}')
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
            id = ""
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

        # Initialize the script master
        self.setSelectedInjectionIndex(self._selected_injection_index)

        # Connect to the simulation view
        self._simulationView.activityChanged.connect(self._onActivityChanged)
        Application.getInstance().getController().activeViewChanged.connect(self._onActivityChanged)

        # Create the injection panel
        CuraApplication.getInstance().addAdditionalComponent('saveButton', self._injectionPanel)

        # Listen for changes to the post-processing scripts
        self._postProcessingPlugin.loadedScriptListChanged.connect(self._loaded_script_list_changed)
        self._postProcessingPlugin.scriptListChanged.connect(self._onPostProcessingScriptsChanged)

        self._injections_changed.emit()

        # Don't need this callback anymore
        CuraApplication.getInstance().mainWindowChanged.disconnect(self._onMainWindowChanged)



    def _onPostProcessingScriptsChanged(self)->None:
        self._injections_changed.emit()
