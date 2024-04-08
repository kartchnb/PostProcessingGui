from ..Script import Script
import re
from UM.Application import Application #To get the current printer's settings.
from UM.Logger import Logger

from typing import List, Tuple

class InsertGcodeAtLayer(Script):
    def __init__(self) -> None:
        super().__init__()

    def getSettingDataString(self) -> str:
        return """{
            "name": "Insert gcode at layer",
            "key": "InsertGcodeAtLayer",
            "metadata": {},
            "version": 2,
            "settings":
            {
                "insert_layer_number":
                {
                    "label": "The layer number",
                    "description": "Enter the layer number to insert gcode before",
                    "type": "int",
                    "value": "10",
                    "minimum_value": "0",
                    "minimum_value_warning": "1"
                },
                "inserted_gcode":
                {
                    "label": "Gcode",
                    "description": "The gcode to insert (separate lines with '\\n' or '|')",
                    "type": "str",
                    "default_value": ""
                }
            }
        }"""

    ##  Copy machine name and gcode flavor from global stack so we can use their value in the script stack
    def initialize(self) -> None:
        super().initialize()


    def execute(self, data: List[str]) -> List[str]:
        """Inserts the gcode commands.

        :param data: List of layers.
        :return: New list of layers.
        """

        insert_layer_number = self.getSettingValueByKey("insert_layer_number")
        Logger.log('d', f'insert_layer_number = {insert_layer_number}')
        inserted_gcode = self.getSettingValueByKey("inserted_gcode")
        inserted_gcode = inserted_gcode.replace('\\n', '\n')
        inserted_gcode = inserted_gcode.replace('|', '\n')

        # Iterate over each layer
        for layer_index, layer in enumerate(data):
            lines = layer.split("\n")

            # Iterate over each line of instruction for each layer in the G-code
            for line_index, line in enumerate(lines):

                if line.startswith(";LAYER:"):
                    current_layer_number_string = line[len(";LAYER:"):]
                    try:
                        current_layer_number = int(current_layer_number_string)
                    # Couldn't cast to int. Something is very wrong with this
                    # g-code data
                    except ValueError:
                        continue

                    Logger.log('d', f'Checking layer {current_layer_number}')
                    if current_layer_number == insert_layer_number:
                        Logger.log('d', 'Inserting gcode')
                        lines.insert(line_index + 1, inserted_gcode)
                        layer = '\n'.join(lines)
                        data[layer_index] = layer
                        return data
                    
        return data
