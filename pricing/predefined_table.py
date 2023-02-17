from pricing.generic_table import GenericTable
import re

shared_types = [
    'e2-micro', 'e2-small', 'e2-medium'
]

field_indexes = {
    "od"    : 1,
    "spot"  : 2,
    "cud1y" : 3,
    "cud3y" : 4
}


class PredefinedTable (GenericTable) :
    def __init__(self, rows, family_name, period) -> None:
        super().__init__(rows, family_name, period)
        self.name="predefined"

    def parse(self, regions) -> list:
        parsed_data = []
        for row in self.rows[1:]:
            prices = row["cells"]
            
            name = prices[0]

            if name in shared_types:
                continue

            cpu = float(prices[self.indexes["cpu"]])
            memory = float(prices[self.indexes["mem"]])

            for region in regions:
                region_alias = region.replace("-", "")
                try:
                    od =  prices[self.indexes["od"]]["priceByRegion"][region_alias]
                    spot =  prices[self.indexes["spot"]]["priceByRegion"][region_alias]
                    cud1y = None
                    cud3y = None
                    if not self.indexes["cud1y"] is None:
                        cud1y =  prices[self.indexes["cud1y"]]["priceByRegion"][region_alias]
                    if not self.indexes["cud3y"] is None:
                        cud3y =  prices[self.indexes["cud3y"]]["priceByRegion"][region_alias]

                    parsed_data.append({
                        "family": self.family_name,
                        "name": name,
                        "cpus": cpu,
                        "memory": memory,
                        "region": region,
                        # apparently, the montly pricing page already has SUD applied
                        #"od": od * 0.8 if family_name in ['n2', 'n2d', 'c2', 'c2d', 'm1', 'm2'] else od,
                        "od": od,
                        "spot": spot,
                        "cud1y": cud1y,
                        "cud3y": cud3y
                    })

                except KeyError:
                    pass

            return parsed_data