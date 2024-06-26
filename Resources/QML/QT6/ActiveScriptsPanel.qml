// Copyright (c) 2024 Brad Kartchner
// Released under the terms of the LGPLv3 or higher.

import QtQuick 6.0
import QtQuick.Controls 6.0
import QtQuick.Layouts 6.0

import UM 1.6 as UM
import Cura 1.7 as Cura

// This component displays buttons for each active layer-based post-processing 
// script as well as a button to insert a new one
RowLayout
{
    visible: manager.showActiveScriptsPanel

    Repeater
    {
        model: manager.activeScriptsModel
        Cura.SecondaryButton
        {
            height: UM.Theme.getSize('action_button').height
            text: modelData['layer_number'].toString()

            tooltip:
            {
                // Return an appropriate tool tip for this button
                var message = 'Center-click to remove this script<br>Right-click to bring up the script settings'
                if (manager.showAddScriptButton)
                {
                    message = 'Left-click to show this layer<br>' + message
                }
                message = 'Script: "' + modelData['script_name'] + '"<br><br>' + message
                return message
            }
            toolTipContentAlignment: UM.Enums.ContentAlignment.AlignLeft

            MouseArea
            {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton

                onClicked:
                {
                    if (mouse.button == Qt.RightButton)
                    {
                        manager.onActiveScriptButtonRightClicked(modelData['script_index'])
                    }
                    else if (mouse.button == Qt.MiddleButton)
                    {
                        manager.onActiveScriptButtonCenterClicked(modelData['script_index'])
                    }
                    else
                    {
                        manager.onActiveScriptButtonLeftClicked(modelData['layer_number'])
                    }
                }
            }
        }
    }

    Cura.PrimaryButton
    {
        height: UM.Theme.getSize('action_button').height
        iconSource: Qt.resolvedUrl('../../Images/InsertButtonIcon.svg')
        fixedWidthMode: false
        
        visible: manager.showAddScriptButton

        tooltip:
        {
            return 'Insert a new post-processing script at the current layer'
        }

        MouseArea
        {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton

            onClicked:
            {
                manager.onAddScriptButtonLeftClicked()
            }
        }
    }
}