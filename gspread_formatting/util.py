# -*- coding: utf-8 -*-
import re 
from math import log, floor

def _build_repeat_cell_request(worksheet, range, cell_format, celldata_field='userEnteredFormat'):
    return {
        'repeatCell': {
            'range': _range_to_gridrange_object(range, worksheet.id),
            'cell': { celldata_field: cell_format.to_props() if cell_format != None else None },
            'fields': ",".join(cell_format.affected_fields(celldata_field)) if cell_format != None else celldata_field
        }
    }

def _fetch_with_updated_properties(spreadsheet, key, params=None):
    try:
        return spreadsheet._properties[key]
    except KeyError:
        metadata = spreadsheet.fetch_sheet_metadata(params)
        spreadsheet._properties.update(metadata['properties'])
        return spreadsheet._properties[key]

_MAGIC_NUMBER = 64
_CELL_ADDR_RE = re.compile(r'([A-Za-z]+)?([1-9]\d*)?')

def rowcol_to_a1(row, col):
    row_label = str(row) if row else ''
    column_label = ''
    if col and col > 0:
        digits = floor(log(col, 26)) + 1 if col > 0 else 0
        remainder = col
        for i in reversed(range(digits)):
            divisor = 26 ** i
            val = floor(remainder / divisor)
            # account for 1-based numbering (A-Z), so not truly base 26
            if i > 0 and (remainder - (val - 1) * divisor) <= sum(map(lambda x: 26 * 26**x, range(i))):
                val -= 1
            # for some values the highest-order digit of log() digits
            # is not needed due to 1-based numbering so we
            # omit that highest-order digit when it would be 0
            if val > 0: 
                column_label += chr(val + _MAGIC_NUMBER)
            remainder -= val * divisor
    return column_label + row_label

def _a1_to_rowcol(label):
    if not label:
        raise ValueError(label)
    m = _CELL_ADDR_RE.match(label)
    if m:
        column_label = m.group(1).upper() if m.group(1) else None
        row = int(m.group(2)) if m.group(2) else None

        if column_label is not None:
            col = 0
            for i, c in enumerate(reversed(column_label)):
                col += (ord(c) - _MAGIC_NUMBER) * (26 ** i)
        else:
            col = None
        return (row, col)
    raise ValueError(label)

def _test_column_conversion(col):
    if _a1_to_rowcol(rowcol_to_a1(None, col))[1] != col:
        print('test failed for ' + str(col))
        print('rowcol: ' + str(rowcol_to_a1(None, col)))
        print('a1:' + str(_a1_to_rowcol(rowcol_to_a1(None, col))))

def _test_all_column_conversions():
    # Maximum number of columns in spreadsheet is 18,278
    # per https://support.google.com/drive/answer/37603
    for i in range(18278):
        _test_column_conversion(i+1)

def _range_to_dimensionrange_object(range, worksheet_id):
    gridrange = _range_to_gridrange_object(range, worksheet_id)
    is_row_range = ('startRowIndex' in gridrange or 'endRowIndex' in gridrange)
    is_column_range = ('startColumnIndex' in gridrange or 'endColumnIndex' in gridrange)
    if is_row_range and is_column_range:
        raise ValueError("Range for dimension must specify only column(s) or only row(s), not both: %s" % range)
    obj = { 'sheetId': worksheet_id }
    if is_row_range:
        obj['dimension'] = 'ROWS'
        if 'endRowIndex' in gridrange:
            obj['endIndex'] = gridrange['endRowIndex']
        if 'startRowIndex' in gridrange:
            obj['startIndex'] = gridrange['startRowIndex']
    if is_column_range:
        obj['dimension'] = 'COLUMNS'
        if 'endColumnIndex' in gridrange:
            obj['endIndex'] = gridrange['endColumnIndex']
        if 'startColumnIndex' in gridrange:
            obj['startIndex'] = gridrange['startColumnIndex']
    return obj

def _range_to_gridrange_object(range, worksheet_id):
    parts = range.split(':')
    start = parts[0]
    end = parts[1] if len(parts) > 1 else ''
    row_offset, column_offset = _a1_to_rowcol(start)
    last_row, last_column = _a1_to_rowcol(end) if end else (row_offset, column_offset)
    # check for illegal ranges
    if (row_offset is not None and last_row is not None and row_offset > last_row):
        raise ValueError(range)
    if (column_offset is not None and last_column is not None and column_offset > last_column):
        raise ValueError(range)
    obj = {
        'sheetId': worksheet_id
    }
    if row_offset is not None:
        obj['startRowIndex'] = row_offset-1
    if last_row is not None:
        obj['endRowIndex'] = last_row
    if column_offset is not None:
        obj['startColumnIndex'] = column_offset-1
    if last_column is not None:
        obj['endColumnIndex'] = last_column
    return obj

def _props_to_component(class_registry, class_alias, value, none_if_empty=False):
    if class_alias not in class_registry:
        raise ValueError("No format component named '%s'" % class_alias)
    cls = class_registry[class_alias]
    kwargs = {}
    for k, v in value.items():
        if isinstance(v, dict):
            if isinstance(cls._FIELDS, dict) and cls._FIELDS.get(k) is not None:
                item_alias = cls._FIELDS[k]
            else:
                item_alias = k
            v = _props_to_component(class_registry, item_alias, v, True)
        if v is not None:
            kwargs[k] = v
    # if our kwargs are empty and there are default values defined
    # for properties in the class, it means to apply all the default values
    # as kwargs.
    if not kwargs and cls._DEFAULTS:
        kwargs = { k: v for k, v in cls._DEFAULTS.items() }
    rv = cls(**kwargs) if (kwargs or not none_if_empty) else None
    return rv

def _ul_repl(m):
    return '_' + m.group(1).lower()

def _underlower(name):
    return name[0].lower() + name[1:]

def _parse_string_enum(name, value, set_of_values, required=False):
    if value is None and required:
        raise ValueError("%s value is required" % name)
    if value is not None and value.upper() not in set_of_values:
        raise ValueError("%s value must be one of: %s" % (name, set_of_values))
    return value.upper() if value is not None else None

def _enforce_type(name, cls, value, required=False):
    if value is None and required:
        raise ValueError("%s value is required" % name)
    if value is not None and not isinstance(value, cls):
        raise ValueError("%s value must be instance of: %s" % (name, cls))
    return value

def _extract_props(value):
    if hasattr(value, 'to_props'):
        return value.to_props()
    return value

def _extract_fieldrefs(name, value, prefix):
    if hasattr(value, 'affected_fields'):
        return value.affected_fields(".".join([prefix, name]))
    elif value is not None:
        return [".".join([prefix, name])]
    else:
        return []

