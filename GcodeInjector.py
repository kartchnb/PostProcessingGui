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
from UM.Trust import Trust, TrustBasics
from UM.i18n import i18nCatalog
from cura import ApplicationMetadata
from cura.CuraApplication import CuraApplication

i18n_catalog = i18nCatalog("cura")

if TYPE_CHECKING:
    from .Script import Script


class GcodeInjector(QObject, Extension):
    """Extension type plugin that enables pre-written scripts to post process g-code files."""



    def __init__(self, parent = None) -> None:
        QObject.__init__(self, parent)
        Extension.__init__(self)

        self._show_injection_panel = False
        self._selected_injection_index = 0
        self._selected_injection_script = None
        self._injections = {}

        # Wait until the application is ready before completing initializing
        CuraApplication.getInstance().mainWindowChanged.connect(self._onMainWindowChanged)

        # Intercept gcode before it is sent to its destination
        Application.getInstance().getOutputDeviceManager().writeStarted.connect(self.onWriteStarted)



    _show_injection_panel_changed = pyqtSignal()
    _loaded_script_list_changed = pyqtSignal()
    _selected_injection_script_changed = pyqtSignal()
    _injections_changed = pyqtSignal()

    

    @cached_property
    def _qmlDir(self)->str:
        plugin_dir = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
        qml_dir = os.path.join(plugin_dir, 'Resources', 'QML', f'QT{PYQT_VERSION}')
        return qml_dir
    


    @cached_property
    def _injectionPanel(self)->QObject:
        qml_file_path = os.path.join(self._qmlDir, 'InjectionPanel.qml')
        component = CuraApplication.getInstance().createQmlComponent(qml_file_path, {'manager': self})
        return component
    


    @cached_property
    def _injectionMenu(self)->QObject:
        qml_file_path = os.path.join(self._qmlDir, 'InjectionMenu.qml')
        component = CuraApplication.getInstance().createQmlComponent(qml_file_path, {'manager': self})
        return component
    


    @cached_property
    def _simulationView(self):
        return Application.getInstance().getController().getView('SimulationView')


    @cached_property
    def _postProcessingPlugin(self):
        return PluginRegistry.getInstance().getPluginObject('PostProcessingPlugin')
    


    @cached_property
    def _availableJsonFileNames(self):
        plugin_dir = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
        json_dir = os.path.join(plugin_dir, 'Resources', 'Json')
        json_wildcard = os.path.join(json_dir, '*.json')
        json_fileNames = glob(json_wildcard)
        return json_fileNames
    


    @cached_property
    def _availableJsonIds(self):
        json_ids = [os.path.splitext(os.path.basename(fileName))[0] for fileName in self._availableJsonFileNames]
        return json_ids
    


    @property
    def _selectedInjectionScript(self):
        if self._selected_injection_script is None:
            self.setSelectedInjectionIndex(self._selected_injection_index)

        return self._selected_injection_script



    def onWriteStarted(self, output_device)->None:
        Message('Write Started').show()



    @pyqtProperty(bool, notify=_show_injection_panel_changed)
    def showInjectionPanel(self)->bool:
        return True # TODO: Delete this line
        return self._show_injection_panel
        
    @showInjectionPanel.setter
    def showInjectionPanel(self, value:bool)->None:
        self._show_injection_panel = value
        self._show_injection_panel_changed.emit()



    @pyqtProperty(list, notify=_loaded_script_list_changed)
    def availableInjectionKeys(self)->list:
        keys = [key for key in self._postProcessingPlugin.loadedScriptList if key in self._availableJsonIds]
        return keys



    @pyqtProperty(list, notify=_loaded_script_list_changed)
    def availableInjectionLabels(self)->list:
        labels = [{'name': self._postProcessingPlugin.getScriptLabelByKey(key) + ' Injection'} for key in self.availableInjectionKeys]
        return labels
    


    def setSelectedInjectionIndex(self, index:int)->None:

        # Create the injection script
        selected_script_key = self.availableInjectionKeys[index]
        new_script = self._postProcessingPlugin._loaded_scripts[selected_script_key]()
        
        # Hack - Overlay customized setting definitions for the script
        setting_data = new_script.getSettingData()
        Logger.log('d', f'setting_data = {setting_data}')
        json_fileName = self._availableJsonFileNames[index]
        with open(json_fileName, 'r') as json_file:
            overlay_setting_data = json.load(json_file, object_pairs_hook = collections.OrderedDict)
            Logger.log('d', f'overlay_setting_data = {overlay_setting_data}')
        
        #setting_data.update(overlay_setting_data)
        def dictOverlay(original, overlay):
            for key, value in overlay.items():
                if isinstance(value, collections.OrderedDict):
                    original[key] = dictOverlay(original.get(key, {}), value)
                else:
                    original[key] = value
            return original

        setting_data = dictOverlay(setting_data, overlay_setting_data)
        Logger.log('d', f'new setting_data = {setting_data}')
        new_script.getSettingData = MethodType(lambda self: setting_data, new_script)

        # Initiailze the script with the overlayed settings definitions
        new_script.initialize()

        # Hack - Don't reslice after script changes because that will mess up the preview display
        new_script._stack.propertyChanged.disconnect(new_script._onPropertyChanged)

        self._selected_injection_index = index
        self._selected_injection_script = new_script
        self._selected_injection_script_changed.emit()

    @pyqtProperty(int, notify=_selected_injection_script_changed, fset=setSelectedInjectionIndex)
    def selectedInjectionIndex(self)->int:
        return self._selected_injection_index



    @pyqtProperty(str, notify=_selected_injection_script_changed)
    def selectedInjectionId(self)->str:
        try:
            id = self._selectedInjectionScript.getDefinitionId()
            Logger.log('d', f'id = {id}')
        except AttributeError:
            id = ""
        return id
    


    @pyqtProperty(str, notify=_selected_injection_script_changed)
    def selectedStackId(self)->str:
        try:
            id = self._selectedInjectionScript.getStackId()
        except AttributeError:
            id = ""
        return id
    


    @pyqtProperty(list, notify=_injections_changed)
    def injectedLayerNumbers(self)->list:
        layer_numbers = list(self._injections.keys())
        layer_numbers.sort()
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
        injection_script_copy = copy.copy(self._selected_injection_script)
        self._injections[layer_number] = injection_script_copy
        self._injections_changed.emit()



    def _removeInjection(self, layer_number:int)->None:
        try:
            del self._injections[layer_number]
            self._injections_changed.emit()
        except IndexError:
            pass



    def _onActivityChanged(self)->None:
        ''' Called when the sliced state of the SimulationView has changed or the view has changed
            If the scene has been sliced, the activity is True, otherwise False '''
        
        try:
            state = CuraApplication.getInstance().getController().getActiveView().getActivity()
        except AttributeError:
            state = False

        self.showInjectionPanel = state



    def _onMainWindowChanged(self)->None:
        ''' The application should be ready at this point '''

        # Connect to the simulation view
        self._simulationView.activityChanged.connect(self._onActivityChanged)
        Application.getInstance().getController().activeViewChanged.connect(self._onActivityChanged)

        # Create the injection panel
        CuraApplication.getInstance().addAdditionalComponent('saveButton', self._injectionPanel)

        # Listen for changes to the post-processing script list
        self._postProcessingPlugin.loadedScriptListChanged.connect(self._loaded_script_list_changed)

        # Don't need this callback anymore
        CuraApplication.getInstance().mainWindowChanged.disconnect(self._onMainWindowChanged)
