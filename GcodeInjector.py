# Copyright (c) 2018 Jaime van Kessel, Ultimaker B.V.
# The PostProcessingPlugin is released under the terms of the LGPLv3 or higher.

import configparser  # The script lists are stored in metadata as serialised config files.
import copy
from functools import cached_property
import importlib.util
import io  # To allow configparser to write to a string.
import os.path
import pkgutil
import sys
from typing import Dict, Type, TYPE_CHECKING, List, Optional, cast

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot
PYQT_VERSION = 6

from UM.Application import Application
from UM.Extension import Extension
from UM.Logger import Logger
from UM.Message import Message
from UM.PluginRegistry import PluginRegistry
from UM.Resources import Resources
from UM.Trust import Trust, TrustBasics
from UM.i18n import i18nCatalog
from cura import ApplicationMetadata
from cura.CuraApplication import CuraApplication

i18n_catalog = i18nCatalog("cura")

if TYPE_CHECKING:
    from .Script import Script


class GcodeInjector(QObject, Extension):
    """Extension type plugin that enables pre-written scripts to post process g-code files."""

    _acceptedScriptKeys = [
        'PauseAtHeight',
    ]


    def __init__(self, parent = None) -> None:
        QObject.__init__(self, parent)
        Extension.__init__(self)

        self._show_injection_panel = False
        self._selected_injection_index = 0
        self._selected_injection_script = None
        self._injections = {}

        # Wait until the application is ready before completing initializing
        CuraApplication.getInstance().mainWindowChanged.connect(self._onMainWindowChanged)



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
    


    @property
    def _selectedInjectionScript(self):
        if self._selected_injection_script is None:
            self.setSelectedInjectionIndex(self._selected_injection_index)

        return self._selected_injection_script



    @pyqtProperty(bool, notify=_show_injection_panel_changed)
    def showInjectionPanel(self)->bool:
        return self._show_injection_panel
    
    @showInjectionPanel.setter
    def showInjectionPanel(self, value:bool)->None:
        self._show_injection_panel = value
        self._show_injection_panel_changed.emit()



    @pyqtProperty(list, notify=_loaded_script_list_changed)
    def availableInjectionKeys(self)->list:
        if len(self._acceptedScriptKeys) > 0:
            return [key for key in self._postProcessingPlugin.loadedScriptList if key in self._acceptedScriptKeys]
        else:
            return self._postProcessingPlugin.loadedScriptList



    @pyqtProperty(list, notify=_loaded_script_list_changed)
    def availableInjectionLabels(self)->list:
        return [{'name': self._postProcessingPlugin.getScriptLabelByKey(key)} for key in self.availableInjectionKeys]
    


    @pyqtProperty(int, notify=_selected_injection_script_changed)
    def selectedInjectionIndex(self)->int:
        return self._selected_injection_index
    
    @pyqtSlot(int)
    def setSelectedInjectionIndex(self, value:int)->None:
        self._selected_injection_index = value
        selected_injection_key = self.availableInjectionKeys[value]
        self._selected_injection_script = self._postProcessingPlugin._loaded_scripts[selected_injection_key]()
        self._selected_injection_script.initialize()
        # Hack to prevent reslicing when script changes are made
        self._selected_injection_script._stack.propertyChanged.disconnect(self._selected_injection_script._onPropertyChanged)
        self._selected_injection_script_changed.emit()



    @pyqtProperty(str, notify=_selected_injection_script_changed)
    def selectedInjectionId(self)->str:
        try:
            id = self._selectedInjectionScript.getDefinitionId()
        except AttributeError:
            id = ""
        return id
    


    @pyqtProperty(str, notify=_selected_injection_script_changed)
    def selectedScriptStackId(self)->str:
        try:
            id = self._selectedInjectionScript.getStackId()
        except AttributeError:
            id = ""
        return id
    


    @pyqtProperty(list, notify=_injections_changed)
    def injectedLayerNumbers(self)->list:
        layer_numbers = list(self._injections.keys())
        layer_numbers.sort()
        Logger.log('d', f'layer_numbers = {layer_numbers}')
        return layer_numbers
    


    @pyqtSlot()
    def onInsertInjectionButtonLeftClicked(self)->None:
        layer_number = self._simulationView.getCurrentLayer()
        Message(f'onInsertInjectionButtonLeftClicked on layer {layer_number}').show()
        self._addInjection(layer_number)



    @pyqtSlot()
    def onInsertInjectionButtonRightClicked(self)->None:
        Message('onInsertInjectionButtonRightClicked').show()
        self._injectionMenu.show()



    @pyqtSlot(int)
    def onExistingInjectionButtonLeftClicked(self, layer_number:int)->None:
        self._simulationView.setLayer(layer_number)
        Message(f'onExistingInjectionButtonLeftClicked for layer {layer_number}').show()



    @pyqtSlot(int)
    def onExistingInjectionButtonLeftClicked(self, layer_number:int)->None:
        Message(f'onExistingInjectionButtonLeftClicked for layer {layer_number}').show()
        pass



    def _addInjection(self, layer_number:int)->None:
        injection_script_copy = copy.copy(self._selected_injection_script)
        self._injections[layer_number] = injection_script_copy
        self._injections_changed.emit()
        Logger.log('d', f'Added injection at layer {layer_number}')



    def _onActivityChanged(self)->None:
        ''' Called when the sliced state of the SimulationView has changed or the view has changed
            If the scene has been sliced, the activity is True, otherwise False '''
        
        try:
            state = CuraApplication.getInstance().getController().getActiveView().getActivity()
        except AttributeError:
            state = False

        self.showInjectionPanel = state
        self.showInjectionPanel = True # TODO: Delete this line



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
