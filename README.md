<a href="https://www.buymeacoffee.com/kartchnb"><img src="https://img.buymeacoffee.com/button-api/?text=Buy me a soda&emoji=&slug=kartchnb&button_colour=40DCA5&font_colour=ffffff&font_family=Bree&outline_colour=000000&coffee_colour=FFDD00" /></a>

[![Github All Releases](https://img.shields.io/github/downloads/kartchnb/PostProcessingGui/total.svg)]()

# Description

This Cura plugin simply adds a GUI to allow you to add layer-focused post-processing scripts directly from Cura's print preview.

This plugin causes a new button to appear when the Preview tab of Cura is shown with a sliced model.  This button allows a script to be added at the currently-displayed layer. ![image](https://github.com/kartchnb/PostProcessingGui/assets/54730012/225addfd-59a5-4dd8-a777-1aa3005b96d3)



Buttons will also appear for post-processing scripts that activate at specific layers in the model. Left-clicking these buttons will activate the corresponding layer (on the Preview tab only).  Right-clicking will bring up the script settings.  Center-clicking will remove the script.

![image](https://github.com/kartchnb/PostProcessingGui/assets/54730012/8283b51e-56b6-4fca-a592-4ef1c4090f8c)


Finally, when saving gcode to a file or sending it to a printer, the plugin will display a rough estimate of when each post-processing script's changes will take effect.  This can be useful, for instance, in determining when a print will pause.

![image](https://github.com/kartchnb/PostProcessingGui/assets/54730012/27e17d06-5c89-42c3-9547-a185831e31c0)

And that's about it.  Not earth-shattering by any means, but it makes my life easier.

# To use

After installation, this plugin can be used by:

1. Slicing a model in Cura
2. Displaying the Preview tab
3. Use the layer slider to find the layer where you need post-processing to be done
4. Click the PostProcessingGui button near the lower-right corner of the Cura window ![image](https://github.com/kartchnb/PostProcessingGui/assets/54730012/225addfd-59a5-4dd8-a777-1aa3005b96d3)
5. Configure the post-processing script as normal
6. Print!

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
