# Copyright (c) 2024 Brad Kartchner
# Released under the terms of the LGPLv3 or higher.

from UM.Logger import Logger
from ..Script import Script

from typing import List



class SwapFilament(Script):
    def __init__(self) -> None:
        super().__init__()



    def getSettingDataString(self) -> str:
        return '''{
            "name": "Swap Filament",
            "key": "SwapFilament",
            "metadata": {},
            "version": 2,
            "settings":
            {
                "insert_layer_number":
                {
                    "label": "The layer number",
                    "description": "Enter the layer number to perform the swap before",
                    "type": "int",
                    "value": "10",
                    "minimum_value": "0",
                    "minimum_value_warning": "1"
                },
                "description":
                {
                    "label": "Description",
                    "description": "A description of the filament to be loaded",
                    "type": "str",
                    "default_value": ""
                }
            }
        }'''



    def initialize(self) -> None:
        ''' Initialize the script '''
        super().initialize()



    def execute(self, gcode: List[str]) -> List[str]:
        ''' Insert the filament swap at the defined layer '''

        # Determine the layer number to insert the gcode at
        insert_layer_number = self.getSettingValueByKey('insert_layer_number')

        # Retrieve the gcode to insert
        # Replace faux newline characters and pipe characters with newlines
        description = self.getSettingValueByKey('description')

        # Iterate over each layer
        for layer_index, layer in enumerate(gcode):
            
            # Split the layer into lines
            lines = layer.split('\n')

            # Iterate over each line of instruction in the layer
            for line_index, line in enumerate(lines):

                # If this is the start of the layer
                if line.startswith(';LAYER:'):

                    # Extract the layer number
                    current_layer_number_string = line[len(';LAYER:'):]
                    try:
                        current_layer_number = int(current_layer_number_string)
                    except ValueError:
                        # If the layer number can't be cast to an integer, 
                        # there is something very wrong with the gcode
                        continue

                    # If this is the layer that needs to be modified
                    if current_layer_number == insert_layer_number:
                        inserted_gcode = f'SWAP DESC={description}\n'

                        # Insert the gcode at this point
                        lines.insert(line_index + 1, inserted_gcode)
                        
                        # Reassemble the layer
                        layer = '\n'.join(lines)

                        # Return the modified layer to the gcode
                        gcode[layer_index] = layer

                        # There's no more need to search through the gcode
                        return gcode
                    
        # If execution reaches this point, the layer could not be found in the
        # gcode
        Logger.log('w', f'SwapFilament post-processing script was unable to find layer #{insert_layer_number} to insert the filament swap')
        return gcode
