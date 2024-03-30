# Adding injections
New "injections" can easily be added for any post-processing script that acts
based on a layer height.

To add a new "injection", create a .json file in this folder and define the 
following entries:

- script_key: the "key" of the script the injection is associated with
  This just needs to match the "key" value of the associated script, which
  can be found by examining the script itself

- layer_number_setting - the setting that identifies the layer number at which
  the post-processing script will take effect
  This setting name can be found by examining the script itself

- (optional) critical_settings - define a set of critical settings and the
  values they must have for the injection to be valid

- (optional) hidden_settings - settings to hide when using the injection menu

# Sample injection file
The following injection file contents defines an injection for the "Pause at 
Height" post-processing script.

Note that the settings require the "Pause at Height" script to be configured to
pause at a layer number rather than height and several settings are hidden when
this injection is used

{
    "script_key": "PauseAtHeight",
    "layer_number_setting": "pause_layer",
    "critical_settings":
    {
        "pause_at": "layer_no"
    },
    "hidden_settings":
    [
        "pause_at",
        "pause_height",
        "pause_layer"
    ]
}