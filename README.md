# Description

This Cura plugin simply adds a GUI to simplify adding layer-based post-processing scripts.

A new button will be appear when in the Preview tab of Cura with a sliced model that will allow a script to be added at the currently-selected layer number.  

Buttons will also appear for post-processing scripts that activate at specific layers in the model. 

Finally, when saving gcode to a file or sending it to a printer, the plugin will display a rough estimate of when each post-processing script's changes will take effect.  This can be useful, for instance, for determining when a print will pause.

And that's about it.  Not earth-shattering by any means, but it makes my life easier.

![image](https://github.com/kartchnb/PostProcessingGui/assets/54730012/4fd307de-c342-4022-99ea-efa8d2d4389f)

# Adding support for additional post-processing scripts

New post-processing scripts can be added to the plugin by simply creating a corresponding .json file in "json" folder and defining the following entries:

- script_key - the "key" of the post-processing script
  This can be found as the "key" value of the associated script, which can be found by examining the script itself

- layer_number_setting - the name of the script setting that defines the layer the post-processing script acts on
  This setting name can be found by examining the script itself

- (optional) critical_settings - a list of critical settings and the values they should be set to in order to be valid

## Sample .json file
The following .json file contents adds the "Pause at Height" post-processing script.

Note that the settings require the "Pause at Height" script to be configured to
pause at a layer number rather than height.

```
{
    "script_key": "PauseAtHeight",
    "layer_number_setting": "pause_layer",
    "critical_settings":
    {
        "pause_at": "layer_no"
    }
}
```
