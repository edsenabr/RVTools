from pricing.generic_table import GenericTable
import re

base_name = re.compile('^(?:.+) (.+)$')

# https://cloud.google.com/compute/docs/machine-types#machine_type_comparison
# Machine series	            vCPUs	Memory (per vCPU)
# E2 General-purpose            2–32	0.5–8 GB
# N1 General-purpose	        1–96	0.9–6.5 GB
# N2 General-purpose	        2–128	0.5–8 GB
# N2D General-purpose	        2–224	0.5–8 GB

cpu_ratio= {
    "e2":  {"cpu_min": 2, "cpu_max": 32, "memory_min": 0.5, "memory_max": 8  },
    "n1":  {"cpu_min": 1, "cpu_max": 96, "memory_min": 0.9, "memory_max": 6.5},
    "n2":  {"cpu_min": 2, "cpu_max": 128,"memory_min": 0.5, "memory_max": 8  },
    "n2d": {"cpu_min": 2, "cpu_max": 224,"memory_min": 0.5, "memory_max": 8  }
}

class BaseTable (GenericTable) :
    def __init__(self, rows, family_name, period, kind) -> None:
        super().__init__(rows, family_name, period)
        self.name = "custom" if kind == "custommachinetypepricing" else "standard"


    def parse(self, regions) -> list:
        parsed_data = []
        for region in regions:
            region_alias = region.replace("-", "")

            region_data = { 
                "name": self.family_name,
                "region": region
            }

            if self.family_name in cpu_ratio:
                region_data.update(cpu_ratio[self.family_name])

            for index, row in enumerate(self.rows[1:]):
                prices = row["cells"]
                price_name = prices[0]
                component = base_name.search(price_name).group(1).lower()

                if component is None:
                    #TODO: erro de parsing, não deveria continuar
                    raise Exception(f"Error parsing unit on row {index} for {self.name} in {self.family_name}")

                self.get_price_for_region(prices, region_data, region_alias, component, "od")
                self.get_price_for_region(prices, region_data, region_alias, component, "spot")

                if not self.indexes["cud1y"] is None:
                    self.get_price_for_region(prices, region_data, region_alias, component, "cud1y")
                if not self.indexes["cud3y"] is None:
                    self.get_price_for_region(prices, region_data, region_alias, component, "cud3y")

            if "vcpus_od" in region_data and "memory_od" in region_data:
                parsed_data.append(region_data)
            else:
                print(f"WARNING! Incomplete {self.name} data for {self.family_name} in {region}")
        return parsed_data

    def get_price_for_region(self, prices, region_data, region_alias, component, commit) -> None:
        try:
            price = float(prices[self.indexes[commit]]["priceByRegion"][region_alias])
            if self.period == "monthly":
                price *= 730
            region_data[f"{component}_{commit}"] = price
        except KeyError:
            pass
        except IndexError:
            pass
        
