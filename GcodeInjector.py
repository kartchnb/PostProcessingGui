# Copyright (c) 2018 Jaime van Kessel, Ultimaker B.V.
# The PostProcessingPlugin is released under the terms of the LGPLv3 or higher.

import configparser  # The script lists are stored in metadata as serialised config files.
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

        # Wait until the application is ready before completing initializing
        CuraApplication.getInstance().mainWindowChanged.connect(self._onMainWindowChanged)



    _show_injection_panel_changed = pyqtSignal()
    _loaded_script_list_changed = pyqtSignal()
    _selected_injection_script_changed = pyqtSignal()

    

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
    


    @pyqtSlot()
    def onInjectButtonLeftClicked(self)->None:
        layer_number = self._simulationView.getCurrentLayer()



    @pyqtSlot()
    def onInjectButtonRightClicked(self)->None:
        self._injectionMenu.show()



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






'''
    @pyqtProperty(str, notify = selectedIndexChanged)
    def selectedScriptDefinitionId(self) -> Optional[str]:
        try:
            return self._script_list[self._selected_script_index].getDefinitionId()
        except IndexError:
            return ""

    @pyqtProperty(str, notify=selectedIndexChanged)
    def selectedScriptStackId(self) -> Optional[str]:
        try:
            return self._script_list[self._selected_script_index].getStackId()
        except IndexError:
            return ""

    def execute(self, output_device) -> None:
        """Execute all post-processing scripts on the gcode."""

        scene = Application.getInstance().getController().getScene()
        # If the scene does not have a gcode, do nothing
        if not hasattr(scene, "gcode_dict"):
            return
        gcode_dict = getattr(scene, "gcode_dict")
        if not gcode_dict:
            return

        # get gcode list for the active build plate
        active_build_plate_id = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
        gcode_list = gcode_dict[active_build_plate_id]
        if not gcode_list:
            return

        if ";POSTPROCESSED" not in gcode_list[0]:
            for script in self._script_list:
                try:
                    gcode_list = script.execute(gcode_list)
                except Exception:
                    Logger.logException("e", "Exception in post-processing script.")
            if len(self._script_list):  # Add comment to g-code if any changes were made.
                gcode_list[0] += ";POSTPROCESSED\n"
            # Add all the active post processor names to data[0]
                pp_name_list = Application.getInstance().getGlobalContainerStack().getMetaDataEntry("post_processing_scripts")
                for pp_name in pp_name_list.split("\n"):
                    pp_name = pp_name.split("]")
                    gcode_list[0] += ";  " + str(pp_name[0]) + "]\n"
            gcode_dict[active_build_plate_id] = gcode_list
            setattr(scene, "gcode_dict", gcode_dict)
        else:
            Logger.log("e", "Already post processed")

    @pyqtSlot(int)
    def setSelectedScriptIndex(self, index: int) -> None:
        if self._selected_script_index != index:
            self._selected_script_index = index
            self.selectedIndexChanged.emit()

    @pyqtProperty(int, notify = selectedIndexChanged)
    def selectedScriptIndex(self) -> int:
        return self._selected_script_index

    @pyqtSlot(int, int)
    def moveScript(self, index: int, new_index: int) -> None:
        if new_index < 0 or new_index > len(self._script_list) - 1:
            return  # nothing needs to be done
        else:
            # Magical switch code.
            self._script_list[new_index], self._script_list[index] = self._script_list[index], self._script_list[new_index]
            self.scriptListChanged.emit()
            self.selectedIndexChanged.emit() #Ensure that settings are updated
            self._propertyChanged()

    @pyqtSlot(int)
    def removeScriptByIndex(self, index: int) -> None:
        """Remove a script from the active script list by index."""

        self._script_list.pop(index)
        if len(self._script_list) - 1 < self._selected_script_index:
            self._selected_script_index = len(self._script_list) - 1
        self.scriptListChanged.emit()
        self.selectedIndexChanged.emit()  # Ensure that settings are updated
        self._propertyChanged()

    def loadAllScripts(self) -> None:
        """Load all scripts from all paths where scripts can be found.

        This should probably only be done on init.
        """

        if self._loaded_scripts: # Already loaded.
            return

        # Make sure a "scripts" folder exists in the main configuration folder and the preferences folder.
        # On some platforms the resources and preferences folders resolve to the same folder,
        # but on Linux they can be different.
        for path in set([os.path.join(Resources.getStoragePath(r), "scripts") for r in [Resources.Resources, Resources.Preferences]]):
            if not os.path.isdir(path):
                try:
                    os.makedirs(path)
                except OSError:
                    Logger.log("w", "Unable to create a folder for scripts: " + path)

        # The PostProcessingPlugin path is for built-in scripts.
        # The Resources path is where the user should store custom scripts.
        # The Preferences path is legacy, where the user may previously have stored scripts.
        resource_folders = [PluginRegistry.getInstance().getPluginPath("PostProcessingPlugin"), Resources.getStoragePath(Resources.Preferences)]
        resource_folders.extend(Resources.getAllPathsForType(Resources.Resources))

        for root in resource_folders:
            if root is None:
                continue
            path = os.path.join(root, "scripts")
            if not os.path.isdir(path):
                continue
            self.loadScripts(path)

    def loadScripts(self, path: str) -> None:
        """Load all scripts from provided path.

        This should probably only be done on init.
        :param path: Path to check for scripts.
        """

        if ApplicationMetadata.IsEnterpriseVersion:
            # Delete all __pycache__ not in installation folder, as it may present a security risk.
            # It prevents this very strange scenario (should already be prevented on enterprise because signed-fault):
            #  - Copy an existing script from the postprocessing-script folder to the appdata scripts folder.
            #  - Also copy the entire __pycache__ folder from the first to the last location.
            #  - Leave the __pycache__ as is, but write malicious code just before the class begins.
            #  - It'll execute, despite that the script has not been signed.
            # It's not known if these reproduction steps are minimal, but it does at least happen in this case.
            install_prefix = os.path.abspath(CuraApplication.getInstance().getInstallPrefix())
            try:
                is_in_installation_path = os.path.commonpath([install_prefix, path]).startswith(install_prefix)
            except ValueError:
                is_in_installation_path = False
            if not is_in_installation_path:
                TrustBasics.removeCached(path)

        scripts = pkgutil.iter_modules(path = [path])
        """Load all scripts in the scripts folders"""
        for loader, script_name, ispkg in scripts:
            # Iterate over all scripts.
            if script_name not in sys.modules:
                try:
                    file_path = os.path.join(path, script_name + ".py")
                    if not self._isScriptAllowed(file_path):
                        Logger.warning("Skipped loading post-processing script {}: not trusted".format(file_path))
                        continue

                    spec = importlib.util.spec_from_file_location(__name__ + "." + script_name,
                                                                  file_path)
                    if spec is None:
                        continue
                    loaded_script = importlib.util.module_from_spec(spec)
                    if spec.loader is None:
                        continue
                    spec.loader.exec_module(loaded_script)  # type: ignore
                    sys.modules[script_name] = loaded_script #TODO: This could be a security risk. Overwrite any module with a user-provided name?

                    loaded_class = getattr(loaded_script, script_name)
                    temp_object = loaded_class()
                    Logger.log("d", "Begin loading of script: %s", script_name)
                    try:
                        setting_data = temp_object.getSettingData()
                        if "name" in setting_data and "key" in setting_data:
                            self._script_labels[setting_data["key"]] = setting_data["name"]
                            self._loaded_scripts[setting_data["key"]] = loaded_class
                        else:
                            Logger.log("w", "Script %s.py has no name or key", script_name)
                            self._script_labels[script_name] = script_name
                            self._loaded_scripts[script_name] = loaded_class
                    except AttributeError:
                        Logger.log("e", "Script %s.py is not a recognised script type. Ensure it inherits Script", script_name)
                    except NotImplementedError:
                        Logger.log("e", "Script %s.py has no implemented settings", script_name)
                except Exception as e:
                    Logger.logException("e", "Exception occurred while loading post processing plugin: {error_msg}".format(error_msg = str(e)))

    loadedScriptListChanged = pyqtSignal()
    @pyqtProperty("QVariantList", notify = loadedScriptListChanged)
    def loadedScriptList(self) -> List[str]:
        return sorted(list(self._loaded_scripts.keys()))

    @pyqtSlot(str, result = str)
    def getScriptLabelByKey(self, key: str) -> Optional[str]:
        return self._script_labels.get(key)

    scriptListChanged = pyqtSignal()
    @pyqtProperty("QStringList", notify = scriptListChanged)
    def scriptList(self) -> List[str]:
        script_list = [script.getSettingData()["key"] for script in self._script_list]
        return script_list

    @pyqtSlot(str)
    def addScriptToList(self, key: str) -> None:
        Logger.log("d", "Adding script %s to list.", key)
        new_script = self._loaded_scripts[key]()
        new_script.initialize()
        self._script_list.append(new_script)
        self.setSelectedScriptIndex(len(self._script_list) - 1)
        self.scriptListChanged.emit()
        self._propertyChanged()

    def _restoreScriptInforFromMetadata(self):
        self.loadAllScripts()
        new_stack = self._global_container_stack
        if new_stack is None:
            return
        self._script_list.clear()
        if not new_stack.getMetaDataEntry("post_processing_scripts"):  # Missing or empty.
            self.scriptListChanged.emit()  # Even emit this if it didn't change. We want it to write the empty list to the stack's metadata.
            self.setSelectedScriptIndex(-1)
            return

        self._script_list.clear()
        scripts_list_strs = new_stack.getMetaDataEntry("post_processing_scripts")
        for script_str in scripts_list_strs.split(
                "\n"):  # Encoded config files should never contain three newlines in a row. At most 2, just before section headers.
            if not script_str:  # There were no scripts in this one (or a corrupt file caused more than 3 consecutive newlines here).
                continue
            script_str = script_str.replace(r"\\\n", "\n").replace(r"\\\\", "\\\\")  # Unescape escape sequences.
            script_parser = configparser.ConfigParser(interpolation=None)
            script_parser.optionxform = str  # type: ignore  # Don't transform the setting keys as they are case-sensitive.
            try:
                script_parser.read_string(script_str)
            except configparser.Error as e:
                Logger.error("Stored post-processing scripts have syntax errors: {err}".format(err = str(e)))
                continue
            for script_name, settings in script_parser.items():  # There should only be one, really! Otherwise we can't guarantee the order or allow multiple uses of the same script.
                if script_name == "DEFAULT":  # ConfigParser always has a DEFAULT section, but we don't fill it. Ignore this one.
                    continue
                if script_name not in self._loaded_scripts:  # Don't know this post-processing plug-in.
                    Logger.log("e",
                               "Unknown post-processing script {script_name} was encountered in this global stack.".format(
                                   script_name=script_name))
                    continue
                new_script = self._loaded_scripts[script_name]()
                new_script.initialize()
                for setting_key, setting_value in settings.items():  # Put all setting values into the script.
                    if new_script._instance is not None:
                        new_script._instance.setProperty(setting_key, "value", setting_value)
                self._script_list.append(new_script)

        self.setSelectedScriptIndex(0)
        # Ensure that we always force an update (otherwise the fields don't update correctly!)
        self.selectedIndexChanged.emit()
        self.scriptListChanged.emit()
        self._propertyChanged()

    def _onGlobalContainerStackChanged(self) -> None:
        """When the global container stack is changed, swap out the list of active scripts."""
        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.disconnect(self._restoreScriptInforFromMetadata)

        self._global_container_stack = Application.getInstance().getGlobalContainerStack()

        if self._global_container_stack:
            self._global_container_stack.metaDataChanged.connect(self._restoreScriptInforFromMetadata)
        self._restoreScriptInforFromMetadata()

    @pyqtSlot()
    def writeScriptsToStack(self) -> None:
        script_list_strs = []  # type: List[str]
        for script in self._script_list:
            parser = configparser.ConfigParser(interpolation = None)  # We'll encode the script as a config with one section. The section header is the key and its values are the settings.
            parser.optionxform = str  # type: ignore # Don't transform the setting keys as they are case-sensitive.
            script_name = script.getSettingData()["key"]
            parser.add_section(script_name)
            for key in script.getSettingData()["settings"]:
                value = script.getSettingValueByKey(key)
                parser[script_name][key] = str(value)
            serialized = io.StringIO()  # ConfigParser can only write to streams. Fine.
            parser.write(serialized)
            serialized.seek(0)
            script_str = serialized.read()
            script_str = script_str.replace("\\\\", r"\\\\").replace("\n", r"\\\n")  # Escape newlines because configparser sees those as section delimiters.
            script_list_strs.append(script_str)

        script_list_string = "\n".join(script_list_strs)  # ConfigParser should never output three newlines in a row when serialised, so it's a safe delimiter.

        if self._global_container_stack is None:
            return

        # Ensure we don't get triggered by our own write.
        self._global_container_stack.metaDataChanged.disconnect(self._restoreScriptInforFromMetadata)

        if "post_processing_scripts" not in self._global_container_stack.getMetaData():
            self._global_container_stack.setMetaDataEntry("post_processing_scripts", "")

        self._global_container_stack.setMetaDataEntry("post_processing_scripts", script_list_string)
        # We do want to listen to other events.
        self._global_container_stack.metaDataChanged.connect(self._restoreScriptInforFromMetadata)

    def _createView(self) -> None:
        """Creates the view used by show popup.

        The view is saved because of the fairly aggressive garbage collection.
        """

        Logger.log("d", "Creating post processing plugin view.")

        self.loadAllScripts()

        # Create the plugin dialog component
        path = os.path.join(cast(str, PluginRegistry.getInstance().getPluginPath("PostProcessingPlugin")), "PostProcessingPlugin.qml")
        self._view = CuraApplication.getInstance().createQmlComponent(path, {"manager": self})
        if self._view is None:
            Logger.log("e", "Not creating PostProcessing button near save button because the QML component failed to be created.")
            return
        Logger.log("d", "Post processing view created.")

        # Create the save button component
        CuraApplication.getInstance().addAdditionalComponent("saveButton", self._view.findChild(QObject, "postProcessingSaveAreaButton"))

    def showPopup(self) -> None:
        """Show the (GUI) popup of the post processing plugin."""

        if self._view is None:
            self._createView()
            if self._view is None:
                Logger.log("e", "Not creating PostProcessing window since the QML component failed to be created.")
                return
        self._view.show()

    def _propertyChanged(self) -> None:
        """Property changed: trigger re-slice

        To do this we use the global container stack propertyChanged.
        Re-slicing is necessary for setting changes in this plugin, because the changes
        are applied only once per "fresh" gcode
        """
        global_container_stack = Application.getInstance().getGlobalContainerStack()
        if global_container_stack is not None:
            global_container_stack.propertyChanged.emit("post_processing_plugin", "value")

    @staticmethod
    def _isScriptAllowed(file_path: str) -> bool:
        """Checks whether the given file is allowed to be loaded"""
        if not ApplicationMetadata.IsEnterpriseVersion:
            # No signature needed
            return True

        dir_path = os.path.split(file_path)[0]  # type: str
        plugin_path = PluginRegistry.getInstance().getPluginPath("PostProcessingPlugin")
        assert plugin_path is not None  # appease mypy
        bundled_path = os.path.join(plugin_path, "scripts")
        if dir_path == bundled_path:
            # Bundled scripts are trusted.
            return True

        trust_instance = Trust.getInstanceOrNone()
        if trust_instance is not None and Trust.signatureFileExistsFor(file_path):
            if trust_instance.signedFileCheck(file_path):
                return True

        return False  # Default verdict should be False, being the most secure fallback


'''