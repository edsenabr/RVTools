from pricing.generic_table import GenericTable
import re

base_re = re.compile('^(.+?) provisioned space$')
class DiskTable (GenericTable) :
    def __init__(self, rows, json_data, period) -> None:
        super().__init__(rows, None, period)
        self.name = "disk"
        self.json_data = json_data

    def parse(self, regions) -> list:
        parsed_data = []
        for index, row in enumerate(self.rows[1:]):
            prices = row["cells"]
            price_name = prices[0]
            definition = base_re.search(price_name)
            if (not definition):
                print(f"Incomplete {self.name} data for {price_name}")
                continue

            name = definition.group(1).lower()
            if name is None:
                print(f"Incomplete {self.name} data for {price_name}")
                continue

            taxonomy = prices[1]["taxonomy"]
            for region in regions:
                try:
                    price = self.get_price_for_taxonomy(taxonomy, region, name)
                    if (not price is None):
                        parsed_data.append({
                            "name": name,
                            "region": region,
                            "price": price
                        })
                except:
                    pass
        return parsed_data

    def get_price_for_taxonomy(self, taxonomy, region, name):
        taxonomy = f"{taxonomy}.regions.{region}.price.-1.nanos".lower().split(".")
        price = self.json_data
        for item in taxonomy:
            if isinstance(price, list):
                price = price[int(item)]
            else:
                price = price[item]
        print(f"{name} price for {taxonomy}: {price}")
        return int(price) / 1000000000
