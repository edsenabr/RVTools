from pricing import GenericTable
from pricing import BaseTable
from pricing import DiskTable
from pricing import PredefinedTable
import json
import re

"""
custom_type_ids = [
	"e2_custommachinetypepricing",
	"n2_custommachinetypepricing",
	"n2d_custommachinetypepricing",
	"n1_custommachinetypepricing",
]

predefined_types_ids = [
	"e2_standard_machine_types",
	"e2_highmem_machine_types",
	"e2_highcpu_machine_types",
	"n2_standard_machine_types",
	"n2_highmem_machine_types",
	"n2_highcpu_machine_types",
	"n2d_standard_machine_types",
	"n2d_highmem_machine_types",
	"n2d_highcpu_machine_types",
	"t2d_standard_machine_types",
	"t2a_standard_machine_types",
	"n1_standard_machine_types",
	"n1_high-memory_machine_types",
	"n1_high-cpu_machine_types",
	"c2_machine_types",
	"c2d_standard_machine_types",
	"c2d_high-memory_machine_types",
	"c2d_high-cpu_machine_types",
	"larger_ultramem",
	"megamem",
	"a2_machine_types",
	"e2_sharedcore_machine_types",
	"n1_sharedcore_machine_types"
]

predefined_types_base_ids = [

]
"""

class TableFactory:
    def from_data(data, period, json_data) -> GenericTable:
        ignored_frames = [
            "n1_extendedmemory",
            "n2_extendedmemory",
            "n2d_extendedmemory",
            "n2_n2d_c2",
            "c2d",
            "combining_commitments_with_reservations",
            "localssdpricing",
            "imagestorage"
        ]

        ignored_families = [
            'g1', 'f1'
        ]


        id =  [sibling['id'] for sibling in data.find_previous_siblings() if (
            sibling.name in ['h3', 'h4'] 
        )][0]

        if id is None or id in ignored_frames:
            return None

        #fixes for error in provided json
        rows = json.loads(
            data.get('layout').replace("\'", "\"")
            .replace("True", "true")
            .replace("False", "false")
            .replace(" (USD)", "")
            .replace("-year", " year")
            .replace("GB", "")
        )["rows"]

        if id == "persistentdisk":
            return DiskTable(rows, json_data, period)

        if id in ["larger_ultramem", "megamem"]:
            family_name = "m1"
        else:
            id_parts = re.match("^([a-z0-9]{2,3})(?:_|-)((?:custommachinetypepricing)?|.+)$", id)
            if not id_parts:
                return None

            family_name = id_parts.group(1)
        if family_name in ignored_families:
            return None



        match rows[0]['cells'][0]:
            case "Machine type":
                return PredefinedTable(rows, family_name, period)

            case "Item":
                table = BaseTable(rows, family_name, period, id_parts.group(2))
                return table

            case _:
                return None