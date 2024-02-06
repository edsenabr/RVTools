import json
import math
import re
from time import time
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from pricing import TableFactory, GCVEFrame, Licenses
from operator import itemgetter
from datetime import datetime


windows = re.compile('.*windows.*', re.IGNORECASE)
sles = re.compile('.*SUSE.*', re.IGNORECASE)
rhel = re.compile('.*Red Hat.*', re.IGNORECASE)
free = re.compile('.*((debian)|(centos)|(coreos)|(ubuntu)).*', re.IGNORECASE)

class PriceList:
    def __init__(self, regions, period, ignore_cache, local_file):
        self.regions = regions
        self.period = period
        self.ignore_cache = ignore_cache
        self.local_file = local_file

        self.lists = { 
            'disk': [],
            'predefined': [],
            'standard': [],
            'custom': [],
            "images" : {}
        }

        if not self.load_from_cache():
            print("Ignoring cache")
            self.load_data()
            self.parse_data()
            self.last_update = time() #TODO: mover para save_cache()
            self.fill_empty_prices()
            self.load_gcve_data()
            self.parse_premium_images()
            self.save_cache()


    def load_from_cache(self):
        if self.ignore_cache:
            return False
        try:
            with open('price_loader.json') as cache:
                data = json.load(cache)
                if not all(region in data['regions'] for region in self.regions):
                    return False
                self.lists = data["lists"]
                self.last_update = datetime.fromtimestamp(data["last_update"]).strftime("%Y-%m-%d")
                self.regions = data['regions']
                print(f"WARNING! using cache file 'price_loader.json' from {self.last_update}\n\t{self.count()}")
                print(f"\tuse -nc to avoid caching or delete the file")
                return True
        except FileNotFoundError:
            return False

    def load_data(self):
        if self.local_file:
            with open('html/all-pricing.html') as local_file:
                html_text = local_file.read()
            with open('html/gcp-compute.json') as local_file:
                json_text = local_file.read()
        else:
            html_text = requests.get('https://cloud.google.com/compute/all-pricing').text
            json_text = requests.get("https://www.gstatic.com/cloud-site-ux/pricing/data/gcp-compute.json").text

        self.soup = BeautifulSoup(html_text, 'html.parser')
        self.raw_data = self.soup.find_all('cloudx-pricing-table')
        self.json_data = json.loads(json_text)


    def count(self):
        return "loaded {predefined} pre-defined types, {custom} customizable families, {disk} disk prices and {os} O.S. prices.".format(
            predefined=len(self.lists['predefined']),
            custom=len(self.lists['custom']),
            disk=len(self.lists['disk']),
            os=len(self.lists["images"])
        )

    def parse_data(self):
        for data in self.raw_data:
            table = TableFactory.from_data(data, self.period, self.json_data)
            if table is None:
                continue    

            pricing = table.parse(self.regions)
            if pricing is None:
                continue

            self.lists[table.name].extend(pricing)

    def fill_empty_prices(self) -> None:
        self.lists['predefined'] = [
            predefined 
                if not predefined['cud1y'] is None 
                else self.fill_empty_price(predefined) 
            for predefined in self.lists['predefined'] 
        ]

    def fill_empty_price(self, item) -> None:
        family_price = [standard for standard in self.lists['standard'] if (
            standard["region"] == item["region"] and 
            standard["name"] == item["family"]
        )]
        if len(family_price) == 0:
            return item
        family_price = family_price[0]
        if "vcpus_cud1y" in family_price:
            item["cud1y"] = (item["cpus"]*family_price["vcpus_cud1y"])+(item["memory"]*family_price["memory_cud1y"])
            item["cud3y"] = (item["cpus"]*family_price["vcpus_cud3y"])+(item["memory"]*family_price["memory_cud3y"])
        return item


    def load_gcve_data(self):
        frame = GCVEFrame()
        pricing = frame.parse(self.regions)
        if not pricing is None:
            self.lists[frame.name].extend(pricing)

    def parse_premium_images(self) -> dict:
        licenses = Licenses(self.soup, self.period)
        if not licenses is None:
            self.lists[licenses.name].update(licenses.parse())

    def save_cache(self):
        with open('price_loader.json', 'w') as cache:
            json.dump(
                {
                    "last_update" : self.last_update,
                    "regions" : self.regions,
                    "lists": self.lists
                }, 
                cache
            )


    def select_price(self, commit, cpus, memory, region, verbose=False):
        cpu = math.ceil(cpus)
        mem = math.ceil(memory/1024)

        if verbose:
            print('commit:\t\t`{commit}`'.format(commit=commit))
        predefined = self.get_predefined_type(commit, region, cpu, mem)
        custom_family = self.get_custom_family(region, cpu, mem, True)
        if not custom_family is None:
            if verbose:
                print('predefined:\t`{name}` costs ${price}'.format(name=predefined['name'], price=predefined[commit]))
                print('custom:\t\t`{name}` costs ${price}'.format(name=custom_family['name'], price=custom_family[commit]))

            if predefined[commit] is None:
                if verbose:
                    print(f'predefined:\tdoes not have {commit}\n')
                return custom_family
            
            if custom_family[commit] < predefined[commit]:
                if verbose:
                    print('cheaper:\tcustom\n')
                return custom_family
            elif verbose:
                    print('cheaper:\tpredefined\n')
        elif verbose:
            print('custom:\t\tnone found; too big?\n')
        return predefined


    def select_disk_price(self, name, region) -> float:
        return [disk["price"] for disk in self.lists['disk'] if (
            disk["region"] == region and 
            disk["name"]==name
        )][0]

    def get_cpu(self, custom, cpu):
        return int(max(cpu, custom["cpu_min"]))

    def get_memory(self, custom, cpu, mem):
        return int(max(mem, math.ceil(self.get_cpu(custom, cpu)*custom['memory_min'])))

    def get_custom_families(self, region:str, cpu:int, mem:int, cud:bool=False) -> dict:
        return sorted(
            [{
                "family": custom['name'],
                'name': "%s-custom-%s-%s" % (custom['name'], self.get_cpu(custom, cpu), self.get_memory(custom, cpu, mem)), 
                "cpus": self.get_cpu(custom, cpu),
                "memory": self.get_memory(custom, cpu, mem),
                "region": region,
                'spot': custom["vcpus_spot"]*self.get_cpu(custom, cpu) + custom["memory_spot"]*self.get_memory(custom, cpu, mem), 
                'od': round((custom["vcpus_od"]*self.get_cpu(custom, cpu) + custom["memory_od"]*self.get_memory(custom, cpu, mem)),2), 
                'cud1y': round((custom["vcpus_cud1y"]*self.get_cpu(custom, cpu) + custom["memory_cud1y"]*self.get_memory(custom, cpu, mem)),2), 
                'cud3y': round((custom["vcpus_cud3y"]*self.get_cpu(custom, cpu) + custom["memory_cud3y"]*self.get_memory(custom, cpu, mem)),2)
            } for custom in self.lists['custom'] if (
                custom["region"] == region and 
                custom["cpu_max"] >= self.get_cpu(custom, cpu) and 
                custom["memory_max"] >= self.get_memory(custom, cpu, mem) / self.get_cpu(custom, cpu)
            )],
            key=itemgetter('cud1y' if cud else 'od')
        )

    def get_custom_family(self, region:str, cpu:int, mem:int, cud:bool=False) -> dict:
        custom = self.get_custom_families(region, cpu, mem, cud)
        return None if len(custom) == 0 else custom[0]

    def get_predefined_type(self, commit:str, region:str, cpu:int, mem:int):
        return [predefined for predefined in sorted(
            self.lists['predefined'],
            key=itemgetter('od')
        ) if (
            predefined["region"] == region and 
            predefined["cpus"] >= cpu and 
            predefined["memory"] >= mem
        )][0]

    def get_gcve_price(self, region:str):
        price = [predefined for predefined in self.lists['predefined'] if (
            predefined["region"] == region and 
            predefined["name"] == "ve1-standard-72"
        )]
        return None if len(price) == 0 else price[0]

    def get_os_price(self, os, cpus): 
        if windows.match(os):
            return self.lists["images"]['windows_per_core'] * cpus
        elif sles.match(os):
            return self.lists["images"]['sles']
        elif rhel.match(os):
            return self.lists["images"]['rhel_less_equal_4vcpus'] if cpus <= 4 else self.lists["images"]['rhel_more_4vcpus']
        else:
            return 0
