import QtQuick 6.0
import QtQuick.Controls 6.0
import QtQuick.Layouts 6.0

import UM 1.6 as UM
import Cura 1.7 as Cura

RowLayout
{
    visible: manager.showInjectionPanel

    Repeater
    {
        model: manager.activeInjectionsModel
        Cura.SecondaryButton
        {
            property int layer_number: modelData['layer_number']

            height: UM.Theme.getSize('action_button').height
            enabled: manager.canAddInjections
            text: layer_number.toString()

            tooltip:
            {
                return modelData['script_name'] + '<br><br>Left-click to go to the layer<br>Right-click to delete the injection'
            }
            toolTipContentAlignment: UM.Enums.ContentAlignment.AlignLeft

            MouseArea
            {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton

                onClicked:
                {
                    if (mouse.button === Qt.RightButton || mouse.button == Qt.MiddleButton)
                    {
                        manager.onExistingInjectionButtonRightClicked(layer_number)
                    }
                    else
                    {
                        manager.onExistingInjectionButtonLeftClicked(layer_number)
                    }
                }
            }
        }
    }

    Cura.PrimaryButton
    {
        height: UM.Theme.getSize('action_button').height
        iconSource: Qt.resolvedUrl('../../Images/InjectorButtonIcon.svg')
        fixedWidthMode: false
        enabled: manager.canAddInjections

        tooltip:
        {
            return manager.selectedInjectionName + ' is active<br><br>Left-click to insert an injection<br>Right-click to modify the injection'
        }

        MouseArea
        {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton

            onClicked:
            {
                if (mouse.button === Qt.RightButton)
                {
                    manager.onInsertInjectionButtonRightClicked()
                }
                else
                {
                    manager.onInsertInjectionButtonLeftClicked()
                }
            }
        }
    }
}