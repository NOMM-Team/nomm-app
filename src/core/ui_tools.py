def get_contrast_color(hex_code: str) -> str:
    """Calcule si le texte doit être noir ou blanc en fonction d'une couleur hexadécimale."""
    hex_code = hex_code.lstrip('#')
    
    # Convert hex to RGB
    r, g, b = [int(hex_code[i:i+2], 16) for i in (0, 2, 4)]
    
    # Calculate relative luminance
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    
    return "#000000" if luminance > 0.5 else "#ffffff"