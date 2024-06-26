// Copyright (c) 2024 Brad Kartchner
// Released under the terms of the LGPLv3 or higher.

import QtQuick 6.0
import QtQuick.Controls 6.0
import QtQuick.Layouts 6.0

import UM 1.6 as UM
import Cura 1.7 as Cura

UM.Dialog
{
    id: dialog

    title: 'Select a script to add'
    width: 500 * screenScaleFactor
    height: 500 * screenScaleFactor
    minimumWidth: 400 * screenScaleFactor
    minimumHeight: 250 * screenScaleFactor
    buttonSpacing: UM.Theme.getSize('default_margin').width
    backgroundColor: UM.Theme.getColor("main_background")

    Item
    {
        width: dialog.width - 2 * UM.Theme.getSize('default_margin').width
        height: parent.height

        RowLayout
        {
            width: parent.width
            height: parent.height
            spacing: UM.Theme.getSize('default_margin').width

            // Display the plugin icon
            Rectangle
            {
                Layout.preferredWidth: icon.width
                Layout.fillHeight: true
                color: UM.Theme.getColor('primary_button')

                Image
                {
                    id: icon
                    source: Qt.resolvedUrl('../../Images/MenuIcon.png')
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }

            ColumnLayout
            {
                id: settingsPanel
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                
                Cura.ComboBox
                {
                    id: scriptSelection
                    Layout.fillWidth: true
                    model: manager.availableScriptsModel
                    textRole: 'script_name'
                    currentIndex: manager.selectedScriptIndex

                    onCurrentIndexChanged:
                    {
                        if (manager.selectedScriptIndex != currentIndex)
                        {
                            manager.selectedScriptIndex = currentIndex
                        }
                    }
                }

                ListView
                {
                    id: listview
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ScrollBar.vertical: UM.ScrollBar {}
                    clip: true
                    spacing: UM.Theme.getSize("default_lining").height

                    model: UM.SettingDefinitionsModel
                    {
                        id: definitionsModel
                        containerId: manager.selectedDefinitionId
                        onContainerIdChanged: definitionsModel.setAllVisible(true)
                        showAll: true
                    }

                    delegate: Loader
                    {
                        id: settingLoader

                        width: listview.width
                        height:
                        {
                            if (provider.properties.enabled == "True" && model.type != undefined)
                            {
                                return UM.Theme.getSize("section").height;
                            }
                            else
                            {
                                return 0
                            }
                        }
                        Behavior on height { NumberAnimation { duration: 100 } }
                        opacity: provider.properties.enabled == "True" ? 1 : 0

                        Behavior on opacity { NumberAnimation { duration: 100 } }
                        enabled: opacity > 0

                        property var definition: model
                        property var settingDefinitionsModel: definitionsModel
                        property var propertyProvider: provider
                        property var globalPropertyProvider: inheritStackProvider

                        //Qt5.4.2 and earlier has a bug where this causes a crash: https://bugreports.qt.io/browse/QTBUG-35989
                        //In addition, while it works for 5.5 and higher, the ordering of the actual combo box drop down changes,
                        //causing nasty issues when selecting different options. So disable asynchronous loading of enum type completely.
                        asynchronous: model.type != "enum" && model.type != "extruder"

                        onLoaded:
                        {
                            settingLoader.item.showRevertButton = false
                            settingLoader.item.showInheritButton = false
                            settingLoader.item.showLinkedSettingIcon = false
                            settingLoader.item.doDepthIndentation = false
                            settingLoader.item.doQualityUserSettingEmphasis = false
                        }

                        sourceComponent:
                        {
                            switch(model.type)
                            {
                                case "int":
                                    return settingTextField
                                case "float":
                                    return settingTextField
                                case "enum":
                                    return settingComboBox
                                case "extruder":
                                    return settingExtruder
                                case "bool":
                                    return settingCheckBox
                                case "str":
                                    return settingTextField
                                case "category":
                                    return settingCategory
                                default:
                                    return settingUnknown
                            }
                        }

                        UM.SettingPropertyProvider
                        {
                            id: provider
                            containerStackId: manager.selectedStackId
                            key: model.key ? model.key : "None"
                            watchedProperties: [ "value", "enabled", "state", "validationState" ]
                            storeIndex: 0
                        }

                        // Specialty provider that only watches global_inherits (we can't filter on what property changed we get events
                        // so we bypass that to make a dedicated provider).
                        UM.SettingPropertyProvider
                        {
                            id: inheritStackProvider
                            containerStack: Cura.MachineManager.activeMachine
                            key: model.key ? model.key : "None"
                            watchedProperties: [ "limit_to_extruder" ]
                        }

                        Connections
                        {
                            target: item

                            function onShowTooltip(text)
                            {
                                tooltip.text = text;
                                var position = settingLoader.mapToItem(settingsPanel, settingsPanel.x, 0);
                                tooltip.show(position);
                                tooltip.target.x = position.x + 1;
                            }

                            function onHideTooltip() { tooltip.hide() }
                        }
                    }
                }
            }
        }

        Cura.PrintSetupTooltip
        {
            id: tooltip
        }

        Component
        {
            id: settingTextField;

            Cura.SettingTextField { }
        }

        Component
        {
            id: settingComboBox;

            Cura.SettingComboBox { }
        }

        Component
        {
            id: settingExtruder;

            Cura.SettingExtruder { }
        }

        Component
        {
            id: settingCheckBox;

            Cura.SettingCheckBox { }
        }

        Component
        {
            id: settingCategory;

            Cura.SettingCategory { }
        }

        Component
        {
            id: settingUnknown;

            Cura.SettingUnknown { }
        }
    }
    rightButtons: 
    [
        Cura.PrimaryButton
        {
            text: 'OK'
            onClicked: dialog.accept()
        },
        Cura.PrimaryButton
        {
            text: 'Cancel'
            onClicked: dialog.reject()
        }
    ]

    onAccepted:
    {
        manager.addScript()
        manager.savePluginSettings()
    }

    onRejected:
    {
        manager.savePluginSettings()
    }
}
