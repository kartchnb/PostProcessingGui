def recursiveDictOverlay(original, overlay):
        ''' Recursively overlay one dict over top of another 
            This differs from the dict.update() function because recursively handles embedded dictionaries
            '''
        
        # Iterate over each entry in the overlay
        for key, value in overlay.items():
            # If this value is an embedded dictionary, then handle it recursively
            if isinstance(value, type(original)):
                original[key] = recursiveDictOverlay(original.get(key, {}), value)

            # For simple values, just overlay the data onto the original dict
            else:
                original[key] = value
                
        return original
