
def openfoam_export(bc_dict, filename='bc_case.json'):
    import json
    with open(filename, 'w') as f:
        json.dump(bc_dict, f, indent=4)
    return filename
