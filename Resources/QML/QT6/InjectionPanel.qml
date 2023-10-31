import QtQuick 6.0
import QtQuick.Controls 6.0
import QtQuick.Layouts 6.0

import UM 1.6 as UM
import Cura 1.7 as Cura

RowLayout
{
    Repeater
    {
        model: manager.injectedLayerNumbers
        Cura.SecondaryButton
        {
            property int layer_number: modelData

            height: UM.Theme.getSize('action_button').height
            text: layer_number.toString()

            tooltip:
            {
                return 'Left-click to go to layer<br><br>Right-click to delete'
            }
            toolTipContentAlignment: UM.Enums.ContentAlignment.AlignLeft

            MouseArea
            {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.RightButton

                onClicked:
                {
                    if (mouse.button === Qt.RightButton)
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