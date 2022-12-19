#!/usr/bin/python3
from opentelemetry.trace import get_tracer
from opentelemetry.trace.propagation import set_span_in_context
import requests
from bs4 import BeautifulSoup
import re

base_price = [
	"e2_machine-types",
	"e2_custommachinetypepricing",
	"n2_machine_types",
	"n2_custommachinetypepricing",
	"n2d_machine_types",
	"n2d_custommachinetypepricing",
	"t2d_machine_types",
	"n1_machine_types",
	"n1_custommachinetypepricing",
	"c2_vcpus_and_memory",
	"a2_machine_types",
    "c2d_vcpus_and_memory",
]

region_codes = {
    "us-central1": "io",
    "us-west1": "ore",
    "us-west2": "la",
    "us-west3": "slc",
    "us-west4": "lv",
    "us-east4": "nv",
    "us-east1": "sc",
    "northamerica-northeast1": "mtreal",
    "northamerica-northeast2": "tor",
    "southamerica-east1": "spaulo",
    "southamerica-west1": "sant",
    "europe-west1": "eu",
    "europe-north1": "fi",
    "europe-west3": "ffurt",
    "europe-west2": "lon",
    "europe-west4": "nether",
    "europe-west6": "zur",
    "europe-west8": "ml",
    "europe-central2": "wsaw",
    "asia-south1": "mbai",
    "asia-south2": "del",
    "asia-southeast1": "sg",
    "asia-southeast2": "jk",
    "australia-southeast1": "syd",
    "australia-southeast2": "mel",
    "asia-east2": "hk",
    "asia-east1": "tw",
    "asia-northeast1": "ja",
    "asia-northeast2": "osa",
    "asia-northeast3": "kr"
}

def cleanup_name(name):
    name = name.strip()
    skylake = re.compile('Skylake Platform only', re.IGNORECASE)
    name = skylake.sub('', name)
    return name

predefined_names = re.compile('^\w{2,3}-.+?(-\d{1,3})?$', re.IGNORECASE)
def is_predefined(name:str): 
    return predefined_names.match(name)

base_name = re.compile('^(.+) (.+)$')
def parse_base_price_name(name:str):
    definition = base_name.search(name)
    return [
        definition.group(1).lower() == "custom",
        definition.group(2).lower()
    ]

def parse_number(row, index, region=None, period=None):
    cleanup = re.compile('[^0-9\.]+')
    column = row.select_one('td:nth-of-type(%s)' % index)
    number = None
    if not column is None:
        text = ""
        if not period is None:
            try:
                text = column.attrs['%s-%s' % (region_codes[region], period)].strip()
            except:
                pass
        else: 
            text = column.text.strip() or column.attrs['default'].strip()
        text = cleanup.sub("", text)
        if text:    
            number = float(text)
    return number



class Frame:
    def __init__(self, id: str, src: str):
        self.id = id
        self.src = src
        self.price_list = None
        self.raw_data = None

    def from_soup(frame):
        ignored_frames = [
            "n1_extendedmemory",
            "n2_extendedmemory",
            "n2d_extendedmemory",
            "n2_n2d_c2",
            "c2d",
            "combining_commitments_with_reservations",
            "localssdpricing"
        ]

        id =  [sibling['id'] for sibling in frame.parent.find_previous_siblings() if (
            sibling.name in ['h3', 'h4'] and 
            sibling['id'] not in ignored_frames
        )][0]

        return None if id is None else Frame(id, frame.get('src'))

    def frame_get(self):
        ctx = set_span_in_context(self.parent_span)
        # url = 'https://cloud.google.com%s' % self.src
        with get_tracer("price_loader").start_as_current_span("frame_get", context=ctx, attributes={'url':self.src}):
            with get_tracer("price_loader").start_as_current_span("frame_load"):
                text = requests.get(self.src).text
                soup = BeautifulSoup(text, 'html.parser')
                self.raw_data = soup.find('table').find('tbody').find_all('tr')
            
            if self.id == 've1-standard-72':
                self.load_gcve_prices()
            elif self.id =='persistentdisk':
                self.load_disk_prices()
            elif self.is_base():
                self.load_custom_prices()
            else:
                self.load_predefined_prices()
        self.price_list.progress_bar.update()


    def is_base(self):
        return self.id in base_price

    @get_tracer("price_loader").start_as_current_span("load_disk_prices")
    def load_disk_prices(self):

        for row in self.raw_data:
            if (row.td is None):
                continue
            name = row.td.text.strip()
            base_re = re.compile('^(.+?) provisioned space$')
            definition = base_re.search(name)
            if (not definition):
                continue

            name = definition.group(1).lower()
            if name is None:
                continue

            for region in self.regions:
                od = parse_number(row, 2, region, self.period)
                if (not od is None):
                    self.price_list.lists['disk'].append({
                        "name": name,
                        "region": region,
                        "price": parse_number(row, 2, region, self.period)
                    })

    @get_tracer("price_loader").start_as_current_span("load_gcve_prices")
    def load_gcve_prices(self):
        for row in self.raw_data:
            if (row.td is None):
                continue
            name = cleanup_name(row.td.text)
            if (name != 've1-standard-72'):
                continue

            for region in self.regions:
                od = parse_number(row, 2, region, 'hourly')
                if (od is None):
                    continue

                self.price_list.lists["predefined"].append({
                    "family": "ve1",
                    "name": name,
                    "cpus": 72,
                    "memory": 768,
                    "region": region,
                    "od": od * 730,
                    "spot": None,
                    "cud1y": parse_number(row.select_one('td:nth-of-type(2)'), 1, region, 'hourly') * 730,
                    "cud3y": parse_number(row.select_one('td:nth-of-type(2)'), 2, region, 'hourly') * 730
                })

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

    ignored_families = [
        'g1', 'f1'
    ]


    @get_tracer("price_loader").start_as_current_span("load_custom_prices")
    def load_custom_prices(self):
        custom = None
        match = re.match("^([a-z0-9]{2,3})(_|-).+$",self.id)
        family_name = match.group(1) if match else None
        if family_name in self.ignored_families:
            return

        for region in self.regions:

            parsed_data = { 
                "name": family_name,
                "region":region
            }

            if family_name in self.cpu_ratio.keys():
                parsed_data.update(self.cpu_ratio[family_name])

            for row in self.raw_data:
                if (row.td is None):
                    continue

                name = row.td.text.strip()


                if (is_predefined(name)):
                    continue

                [custom, unit] = parse_base_price_name(name)

                # print("%s|%s|%s|%s" % (family_name, name, unit, self.id))
                if unit is None:
                    continue
            
                od = parse_number(row, 2, region, self.period)
                if od is None:
                    continue
                parsed_data.update({
                    # apparently, the montly pricing page already has SUD applied
                    #"{unit}_od".format(unit=unit): od * 0.8 if family_name in ['n2', 'n2d', 'c2', 'c2d', 'm1', 'm2'] else od,
                    "{unit}_od".format(unit=unit): od,
                    "{unit}_spot".format(unit=unit): parse_number(row, 3, region, self.period),
                    "{unit}_cud1y".format(unit=unit): parse_number(row, 4, region, self.period),
                    "{unit}_cud3y".format(unit=unit): parse_number(row, 5, region, self.period)
                })
            if "vcpus_od" in parsed_data  and "memory_od" in parsed_data:
                if custom:
                    self.price_list.lists['custom'].append(parsed_data)
                else:
                    self.price_list.lists['standard'].append(parsed_data)
            else:
                pass

    shared_types = [
        'e2-micro', 'e2-small', 'e2-medium'
    ]

    @get_tracer("price_loader").start_as_current_span("load_predefined_prices")
    def load_predefined_prices(self):
        for row in self.raw_data:
            if (row.td is None):
                continue

            
            name = cleanup_name(row.td.text)
            if (not is_predefined(name)):
                continue

            if name in self.shared_types:
                continue

            match = re.match("^([a-z0-9]{2,3})(_|-).+$",name)
            family_name = match.group(1) if match else None
            if family_name in self.ignored_families:
                return
            
            cpu = parse_number(row, 2)
            memory = parse_number(row, 3)

            for region in self.regions:
                od = parse_number(row, 4, region, self.period)
                if (not od is None):
                    self.price_list.lists['predefined'].append({
                        "family": family_name,
                        "name": name,
                        "cpus": cpu,
                        "memory": memory,
                        "region": region,
                        # apparently, the montly pricing page already has SUD applied
                        #"od": od * 0.8 if family_name in ['n2', 'n2d', 'c2', 'c2d', 'm1', 'm2'] else od,
                        "od": od,
                        "spot": parse_number(row, 5, region, self.period),
                        "cud1y": parse_number(row, 6, region, self.period),
                        "cud3y": parse_number(row, 7, region, self.period)
                    })
