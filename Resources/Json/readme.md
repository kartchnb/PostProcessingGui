# Adding post-processing scripts

New post-processing scripts can be added to the GUI by simply creating a corresponding .json file in this folder and defining the following entries:

- script_key - the "key" of the post-processing script
  This can be found as the "key" value of the associated script, which can be found by examining the script itself

- layer_number_setting - the name of the script setting that defines the layer the post-processing script acts on
  This setting name can be found by examining the script itself

- (optional) critical_settings - a list of critical settings and the values they should be set to for the GUI

# Sample .json file
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
