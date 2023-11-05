import QtQuick 6.0
import QtQuick.Controls 6.0
import QtQuick.Layouts 6.0

import UM 1.6 as UM
import Cura 1.7 as Cura

RowLayout
{
    Repeater
    {
        model: manager.injectionModel
        Cura.SecondaryButton
        {
            property int layer_number: modelData['layer_number']

            height: UM.Theme.getSize('action_button').height
            text: layer_number.toString()

            tooltip:
            {
                return modelData['script_name'] + '<br><br>Left-click to go to layer<br>Right-click to delete'
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
            return manager.selectedInjectionName
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