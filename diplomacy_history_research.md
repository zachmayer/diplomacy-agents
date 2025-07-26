# Diplomacy Package History Data Structures Research Report

## Overview

This report provides comprehensive technical details about the `order_history`, `result_history`, and `state_history` properties in the diplomacy package to support implementation of strongly-typed property getters.

## 1. Order History

### Data Structure

- **Type**: `diplomacy.utils.sorted_dict.SortedDict`
- **Format**: `{short_phase_name => {power_name => [orders]}}`
- **Documentation**: "Contains the history of orders from each player from the beginning of the game. Sorted dict mapping a short phase name to a dictionary of orders (powers names as keys, powers orders as values)."

### Key Details

- **Phase Keys**: `diplomacy.utils.common.str_cmp_class.<locals>.StringComparator` objects
  - **StringComparator**: A wrapper class around strings that enables custom sorting. Created by the `str_cmp_class()` function, it wraps phase strings like `'S1901M'` with chronological comparison logic to ensure phases are automatically sorted oldest to newest.
  - String representation: `'S1901M'`, `'F1901M'`, `'W1901A'`, `'S1902M'`
  - These are automatically sorted chronologically (oldest to newest)
- **Power Names**: Standard strings like `'AUSTRIA'`, `'ENGLAND'`, `'FRANCE'`, etc.
- **Orders**: List of strings in DATC format
  - Examples: `['A BUD S A VIE - TRI', 'F TRI - VEN', 'A VIE - TRI']`
  - Empty lists `[]` for adjustment phases when no orders submitted

### Raw Engine Data

```python
# What you get directly from game.order_history
{
    'S1901M': {
        'AUSTRIA': ['A BUD - GAL', 'F TRI S A ROM - VEN', 'A VIE S A BUD - TRI'],
        'ENGLAND': ['F EDI - NWG', 'F LON - WAL', 'A LVP - EDI'],
        'FRANCE': ['F BRE S F LON - ENG', 'A MAR S F BRE - GAS', 'A PAR S A MAR - GAS'],
        'GERMANY': ['A BER S A MUN', 'F KIE - HEL', 'A MUN S A MAR - BUR'],
        'ITALY': ['F NAP - ROM', 'A ROM S A VEN - TUS', 'A VEN S A ROM'],
        'RUSSIA': ['A MOS H', 'F SEV - ARM', 'F STP/SC - FIN', 'A WAR S A VIE - GAL'],
        'TURKEY': ['F ANK S A SMY - ARM', 'A CON - SMY', 'A SMY S F ANK'],
    },
    'F1901M': {
        'AUSTRIA': ['A GAL - VIE', 'F TRI H', 'A VIE - BUD'],
        'ENGLAND': ['F NWG - NWY', 'F WAL - ENG', 'A EDI - YOR'],
        'FRANCE': ['F BRE - MAO', 'A MAR H', 'A PAR - PIC'],
        'GERMANY': ['A BER - PRU', 'F HEL - KIE', 'A MUN - BOH'],
        'ITALY': ['F ROM - TUS', 'A ROM - NAP', 'A VEN - PIE'],
        'RUSSIA': ['A MOS - STP', 'F ARM - BLA', 'F FIN - SWE', 'A WAR - GAL'],
        'TURKEY': ['F ANK - BLA', 'A SMY - CON', 'A SMY - ARM'],
    },
    'W1901A': {
        'AUSTRIA': [],  # Raw engine provides empty lists for all powers
        'ENGLAND': [],
        'FRANCE': [],
        'GERMANY': [],
        'ITALY': [],
        'RUSSIA': [],
        'TURKEY': [],
    }
}
```

### Desired Output Format
```python
# What your property getter should return after processing
{
    'S1901M': {
        Power.AUSTRIA: ('A BUD - GAL', 'F TRI S A ROM - VEN', 'A VIE S A BUD - TRI'),
        Power.ENGLAND: ('F EDI - NWG', 'F LON - WAL', 'A LVP - EDI'),
        Power.FRANCE: ('F BRE S F LON - ENG', 'A MAR S F BRE - GAS', 'A PAR S A MAR - GAS'),
        Power.GERMANY: ('A BER S A MUN', 'F KIE - HEL', 'A MUN S A MAR - BUR'),
        Power.ITALY: ('F NAP - ROM', 'A ROM S A VEN - TUS', 'A VEN S A ROM'),
        Power.RUSSIA: ('A MOS H', 'F SEV - ARM', 'F STP/SC - FIN', 'A WAR S A VIE - GAL'),
        Power.TURKEY: ('F ANK S A SMY - ARM', 'A CON - SMY', 'A SMY S F ANK'),
    },
    'F1901M': {
        Power.AUSTRIA: ('A GAL - VIE', 'F TRI H', 'A VIE - BUD'),
        Power.ENGLAND: ('F NWG - NWY', 'F WAL - ENG', 'A EDI - YOR'),
        Power.FRANCE: ('F BRE - MAO', 'A MAR H', 'A PAR - PIC'),
        Power.GERMANY: ('A BER - PRU', 'F HEL - KIE', 'A MUN - BOH'),
        Power.ITALY: ('F ROM - TUS', 'A ROM - NAP', 'A VEN - PIE'),
        Power.RUSSIA: ('A MOS - STP', 'F ARM - BLA', 'F FIN - SWE', 'A WAR - GAL'),
        Power.TURKEY: ('F ANK - BLA', 'A SMY - CON', 'A SMY - ARM'),
    },
    'W1901A': {}  # Empty dict (empty lists removed) shows phase existed but no orders
}
```

### Typing Requirements

- Phase keys: Convert `StringComparator` to standard Python `str` type  
- Power names: Convert to your `Power` enum
- Orders: Already strings, can use your `Orders` type alias

## 2. Result History

### Data Structure

- **Type**: `diplomacy.utils.sorted_dict.SortedDict`
- **Format**: `{short_phase_name => {unit => [results]}}`
- **Documentation**: "Contains the history of orders results for all played phases. Dictionary of order results maps a unit to a list of results."

### Key Details

- **Phase Keys**: Same `StringComparator` objects as order_history
- **Unit Keys**: Strings like `'A BUD'`, `'F TRI'`, `'A VIE'`
  - Format: `{UnitType} {Location}` (already matches your `parse_unit` function)
- **Results**: Lists of `diplomacy.utils.order_results.OrderResult` objects
  - Examples: `[bounce]`, `[void]`, `[]` (empty for successful orders)
  - **Complete list of possible result types**: `OK` (empty, successful), `NO_CONVOY`, `BOUNCE`, `VOID`, `CUT`, `DISLODGED`, `DISRUPTED`, `DISBAND`, `MAYBE`

### Suggested OrderResult Enum

```python
class OrderResult(PrettyStrEnum):
    """Order execution results."""
    
    OK = ""              # Successful execution (represented as empty list)
    NO_CONVOY = "no convoy"
    BOUNCE = "bounce"
    VOID = "void"
    CUT = "cut"
    DISLODGED = "dislodged"
    DISRUPTED = "disrupted"
    DISBAND = "disband"
    MAYBE = "maybe"
```

### Raw Engine Data
```python
# What you get directly from game.result_history
{
    'S1901M': {
        'A BUD': [],              # successful (empty list)
        'A VIE': [10003:void],    # OrderResult object (repr shows code:message)
        'F TRI': [10003:void],    # OrderResult object
        'F EDI': [],              # successful (empty list)
        'F LON': [],              # successful (empty list)
        'A LVP': [],              # successful (empty list)
        'F BRE': [10003:void],    # OrderResult object
        'A MAR': [10003:void],    # OrderResult object
        'A PAR': [10003:void],    # OrderResult object
        'F KIE': [],              # successful (empty list)
        'A BER': [],              # successful (empty list)
        'A MUN': [10003:void],    # OrderResult object
        'F NAP': [10002:bounce],  # OrderResult object
        'A ROM': [10003:void],    # OrderResult object
        'A VEN': [],              # successful (empty list)
        'A WAR': [10003:void],    # OrderResult object
        'A MOS': [],              # successful (empty list)
        'F SEV': [],              # successful (empty list)
        'F STP/SC': [],           # successful (empty list)
        'F ANK': [10003:void],    # OrderResult object
        'A CON': [10002:bounce],  # OrderResult object
        'A SMY': [],              # successful (empty list)
    },
    'W1901A': {
        'WAIVE': [10003:void]     # Special case for adjustment phase
    }
}
```

### Desired Output Format
```python
# What your property getter should return after processing
{
    'S1901M': {
        # Note: Units with empty result lists (successful orders) are removed
        (UnitType.ARMY, Location.VIE): (OrderResult.VOID,),
        (UnitType.FLEET, Location.TRI): (OrderResult.VOID,),
        (UnitType.FLEET, Location.BRE): (OrderResult.VOID,),
        (UnitType.ARMY, Location.MAR): (OrderResult.VOID,),
        (UnitType.ARMY, Location.PAR): (OrderResult.VOID,),
        (UnitType.ARMY, Location.MUN): (OrderResult.VOID,),
        (UnitType.FLEET, Location.NAP): (OrderResult.BOUNCE,),
        (UnitType.ARMY, Location.ROM): (OrderResult.VOID,),
        (UnitType.ARMY, Location.WAR): (OrderResult.VOID,),
        (UnitType.FLEET, Location.ANK): (OrderResult.VOID,),
        (UnitType.ARMY, Location.CON): (OrderResult.BOUNCE,),
    },
    'W1901A': {
        # Special case: WAIVE is kept even though it has non-empty results
        'WAIVE': (OrderResult.VOID,)
    }
}
```

### Special Cases

- Adjustment phases may contain special units like `'WAIVE'` with `[void]` results
- Empty result lists `[]` indicate successful order execution, but these entries are removed for brevity (per implementation point #3)

### Typing Requirements

- Phase keys: Convert to `str`
- Unit keys: Use your `parse_unit()` function to get `(UnitType, Location)`
- Results: Convert `OrderResult` objects to your `OrderResult` enum values

## 3. State History

### Data Structure

- **Type**: `diplomacy.utils.sorted_dict.SortedDict` 
- **Format**: `{short_phase_name => state}`
- **Documentation**: "History of previous game states (returned by method get_state()) for this game. Each game state is associated to a timestamp."

### Key Details

- **Phase Keys**: Same `StringComparator` objects as other histories
- **Simplified State Structure**: Focus on strategically relevant data only:

  ```python
  {
    'units': dict,             # {power_name: [unit_list]}
    'centers': dict,           # {power_name: [location_list]}
    'retreats': dict,          # Dislodged units data
    'builds': dict            # Build/disband requirements
  }
  ```

### Key Nested Structures

#### Raw Engine Format
```python
# units structure from raw engine
'units': {
    'AUSTRIA': ['A BUD', 'A VIE', 'F TRI'],         # Raw unit strings
    'ENGLAND': ['F EDI', 'F LON', 'A LVP'],
    'FRANCE': ['F BRE', 'A MAR', 'A PAR'],
    'GERMANY': ['F KIE', 'A BER', 'A MUN'],
    'ITALY': ['F NAP', 'A ROM', 'A VEN'],
    'RUSSIA': ['A WAR', 'A MOS', 'F SEV', 'F STP/SC'],
    'TURKEY': ['F ANK', 'A CON', 'A SMY'],
}

# centers structure from raw engine
'centers': {
    'AUSTRIA': ['BUD', 'TRI', 'VIE'],               # Raw location strings
    'ENGLAND': ['EDI', 'LON', 'LVP'],
    'FRANCE': ['BRE', 'MAR', 'PAR'],
    'GERMANY': ['BER', 'KIE', 'MUN'],
    'ITALY': ['NAP', 'ROM', 'VEN'],
    'RUSSIA': ['MOS', 'SEV', 'STP', 'WAR'],
    'TURKEY': ['ANK', 'CON', 'SMY'],
}
```

#### Desired Output Format
```python
# units structure after processing
'units': {
    Power.AUSTRIA: ((UnitType.ARMY, Location.BUD), (UnitType.ARMY, Location.VIE), (UnitType.FLEET, Location.TRI)),
    Power.ENGLAND: ((UnitType.FLEET, Location.EDI), (UnitType.FLEET, Location.LON), (UnitType.ARMY, Location.LVP)),
    Power.FRANCE: ((UnitType.FLEET, Location.BRE), (UnitType.ARMY, Location.MAR), (UnitType.ARMY, Location.PAR)),
    Power.GERMANY: ((UnitType.FLEET, Location.KIE), (UnitType.ARMY, Location.BER), (UnitType.ARMY, Location.MUN)),
    Power.ITALY: ((UnitType.FLEET, Location.NAP), (UnitType.ARMY, Location.ROM), (UnitType.ARMY, Location.VEN)),
    Power.RUSSIA: ((UnitType.ARMY, Location.WAR), (UnitType.ARMY, Location.MOS), (UnitType.FLEET, Location.SEV), (UnitType.FLEET, Location.STP_SC)),
    Power.TURKEY: ((UnitType.FLEET, Location.ANK), (UnitType.ARMY, Location.CON), (UnitType.ARMY, Location.SMY)),
}

# centers structure after processing  
'centers': {
    Power.AUSTRIA: (Location.BUD, Location.TRI, Location.VIE),
    Power.ENGLAND: (Location.EDI, Location.LON, Location.LVP),
    Power.FRANCE: (Location.BRE, Location.MAR, Location.PAR),
    Power.GERMANY: (Location.BER, Location.KIE, Location.MUN),
    Power.ITALY: (Location.NAP, Location.ROM, Location.VEN),
    Power.RUSSIA: (Location.MOS, Location.SEV, Location.STP, Location.WAR),
    Power.TURKEY: (Location.ANK, Location.CON, Location.SMY),
}
```

### Raw Engine Data
```python
# What you get directly from game.state_history[phase]
{
    'S1901M': {
        'timestamp': 1753516910749465,      # Raw engine includes these
        'zobrist_hash': 12345678901234567890,
        'note': '',
        'name': 'standard',
        'units': {
            'AUSTRIA': ['A BUD', 'A VIE', 'F TRI'],
            'ENGLAND': ['F EDI', 'F LON', 'A LVP'],
            'FRANCE': ['F BRE', 'A MAR', 'A PAR'],
            'GERMANY': ['F KIE', 'A BER', 'A MUN'],
            'ITALY': ['F NAP', 'A ROM', 'A VEN'],
            'RUSSIA': ['A WAR', 'A MOS', 'F SEV', 'F STP/SC'],
            'TURKEY': ['F ANK', 'A CON', 'A SMY'],
        },
        'centers': {
            'AUSTRIA': ['BUD', 'TRI', 'VIE'],
            'ENGLAND': ['EDI', 'LON', 'LVP'],
            'FRANCE': ['BRE', 'MAR', 'PAR'],
            'GERMANY': ['BER', 'KIE', 'MUN'],
            'ITALY': ['NAP', 'ROM', 'VEN'],
            'RUSSIA': ['MOS', 'SEV', 'STP', 'WAR'],
            'TURKEY': ['ANK', 'CON', 'SMY'],
        },
        'retreats': {},
        'homes': { /* home supply centers */ },
        'influence': { /* influence data */ },
        'civil_disorder': [],
        'builds': { /* build requirements when relevant */ }
    }
}
```

### Desired Output Format
```python
# What your property getter should return after processing
{
    'S1901M': {
        'units': {
            Power.AUSTRIA: ((UnitType.ARMY, Location.BUD), (UnitType.ARMY, Location.VIE), (UnitType.FLEET, Location.TRI)),
            Power.ENGLAND: ((UnitType.FLEET, Location.EDI), (UnitType.FLEET, Location.LON), (UnitType.ARMY, Location.LVP)),
            Power.FRANCE: ((UnitType.FLEET, Location.BRE), (UnitType.ARMY, Location.MAR), (UnitType.ARMY, Location.PAR)),
            Power.GERMANY: ((UnitType.FLEET, Location.KIE), (UnitType.ARMY, Location.BER), (UnitType.ARMY, Location.MUN)),
            Power.ITALY: ((UnitType.FLEET, Location.NAP), (UnitType.ARMY, Location.ROM), (UnitType.ARMY, Location.VEN)),
            Power.RUSSIA: ((UnitType.ARMY, Location.WAR), (UnitType.ARMY, Location.MOS), (UnitType.FLEET, Location.SEV), (UnitType.FLEET, Location.STP_SC)),
            Power.TURKEY: ((UnitType.FLEET, Location.ANK), (UnitType.ARMY, Location.CON), (UnitType.ARMY, Location.SMY)),
        },
        'centers': {
            Power.AUSTRIA: (Location.BUD, Location.TRI, Location.VIE),
            Power.ENGLAND: (Location.EDI, Location.LON, Location.LVP),
            Power.FRANCE: (Location.BRE, Location.MAR, Location.PAR),
            Power.GERMANY: (Location.BER, Location.KIE, Location.MUN),
            Power.ITALY: (Location.NAP, Location.ROM, Location.VEN),
            Power.RUSSIA: (Location.MOS, Location.SEV, Location.STP, Location.WAR),
            Power.TURKEY: (Location.ANK, Location.CON, Location.SMY),
        },
        'retreats': {},  # Empty dict preserved to show phase had no retreats
        'builds': {}     # Empty dict preserved to show phase had no builds
    }
}
```

### Typing Requirements

- Phase keys: Convert to `str`
- Power names: Convert to your `Power` enum  
- Unit strings: Use `parse_unit()` for `(UnitType, Location)` tuples
- Location strings: Convert to your `Location` enum

## 4. Common Patterns

### Chronological Sorting

All three histories use `SortedDict` with phase-aware sorting that automatically maintains chronological order (oldest to newest). The diplomacy package's `compare_phases` function handles this.

### Phase Key Format

- Spring: `'S1901M'` (Spring 1901 Movement)
- Fall: `'F1901M'` (Fall 1901 Movement)  
- Winter: `'W1901A'` (Winter 1901 Adjustment)
- Retreats: `'S1901R'` (Spring 1901 Retreats)

### Power Ordering

Powers are ordered alphabetically: `AUSTRIA`, `ENGLAND`, `FRANCE`, `GERMANY`, `ITALY`, `RUSSIA`, `TURKEY`

## 5. Implementation Recommendations

### Suggested Type Signatures

```python
@property
def order_history(self) -> dict[str, dict[Power, Orders]]:
    """Order history sorted chronologically (oldest to newest)."""

@property  
def result_history(self) -> dict[str, dict[tuple[UnitType, Location], tuple[OrderResult, ...]]]:
    """Result history sorted chronologically (oldest to newest)."""

@property
def state_history(self) -> dict[str, dict[str, Any]]:
    """State history sorted chronologically (oldest to newest). 
    
    Contains simplified state with keys: 'units', 'centers', 'retreats', 'builds'.
    """
```

### Key Implementation Points

1. **Maintain Chronological Order**: Preserve the `SortedDict` ordering when converting
2. **Type Conversion**: Convert raw strings to your enums (`Power`, `Location`, `UnitType`, `OrderResult`)
3. **Remove Empty Lists**: For brevity, remove any dictionary keys that map to empty lists. Keep the phase/container as an empty dictionary to explicitly show it existed but had no data.
4. **Handle Empty Cases**: Account for empty lists in adjustment phases (which become empty dictionaries after applying rule #3)
5. **Parse Units**: Use your existing `parse_unit()` function for unit strings
6. **Result Objects**: Convert `OrderResult` objects to your `OrderResult` enum values
7. **Special Cases**: Handle `'WAIVE'` units in adjustment phases appropriately
8. **State Simplification**: Extract only strategically relevant fields from state history

### Runtime Validation Strategy

Follow your existing pattern of runtime type checking rather than using casts. The diplomacy package data is well-structured and consistent, making runtime validation straightforward.

## 6. Phase Filtering Considerations

All phase types provide strategically valuable information:

- **Movement Phases** (`S1901M`, `F1901M`): Core tactical decisions, unit movements, battles
- **Retreat Phases** (`S1901R`, `F1901R`): Dislodgment resolution, unit preservation decisions  
- **Adjustment Phases** (`W1901A`): Builds/disbands reflecting supply center changes

**Recommendation**: Keep all phases as each provides unique strategic insights for analysis.

## 7. References

You can use your tools to check these references for further information.
Use your web tool for links and your code inspection tools for the source code.

- [Diplomacy Package Documentation](https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.game.html)
- Source files examined:
  - `.venv/lib/python3.12/site-packages/diplomacy/engine/game.py`
  - `.venv/lib/python3.12/site-packages/diplomacy/utils/sorted_dict.py`
  - `.venv/lib/python3.12/site-packages/diplomacy/tests/test_game.py`
  - `.venv/lib/python3.12/site-packages/diplomacy/utils/order_results.py`
  - `.venv/lib/python3.12/site-packages/diplomacy/utils/common.py`
