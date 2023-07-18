from pricing.generic_table import GenericTable
import re
import traceback

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
            
            if price_name in [
                "Extreme provisioned IOPS",
                "Hyperdisk Extreme provisioned IOPS",
                "Hyperdisk Throughput provisioned throughput"
            ]:
                continue

            definition = base_re.search(price_name)
            if not definition:
                print(f"WARNING! Incomplete {self.name} data for {price_name}")
                continue

            name = definition.group(1).lower()
            if name is None:
                print(f"WARNING! Incomplete {self.name} data for {price_name}")
                continue
            try:
                taxonomy = prices[1]["taxonomy"]
            except Exception as ex:
                print(f"WARNING! Failed to load taxonomy {self.name} data for {price_name}")
                continue

            for region in regions:
                try:
                    price = self.get_price_for_taxonomy(taxonomy, region, name)
                    if (price is None):
                        print(f"WARNING! Price not found for taxonomy {taxonomy} in region {region}")
                    else:
                        parsed_data.append({
                            "name": name,
                            "region": region,
                            "price": price
                        })
                except Exception as e:
                    print(f"WARNING! Price not found for taxonomy {taxonomy} in region {region}: {traceback.format_exc()}")
                    continue
        return parsed_data

    def get_price_for_taxonomy(self, taxonomy, region, name):
        region_alias = re.sub(string=region, pattern="-([0-9])$", repl="\\1")
        taxonomy = f"{taxonomy}.regions.{region_alias}.price.-1.nanos".lower().split(".")
        price = self.json_data
        for item in taxonomy:
            if isinstance(price, list):
                price = price[int(item)]
            else:
                price = price[item]
        return int(price) / 1000000000
