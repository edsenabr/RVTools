import argparse
from pricing.base_table import BaseTable
from pricing.predefined_table import PredefinedTable
from pricing.disk_table import DiskTable
from pricing.generic_table import GenericTable
from pricing.table_factory import TableFactory
from pricing.gcve_frame import GCVEFrame
from pricing.licenses_text import Licenses
from pricing.price_list import PriceList

def parse_args(require_sheet=False):
    parser = argparse.ArgumentParser(True)
    parser.add_argument("-r", "--regions", nargs='*', help="region to be loaded", required=True)
    parser.add_argument("-p", "--period", nargs='?', help="regions to be loaded", default="monthly" , choices=['monthly', 'hourly'])
    parser.add_argument("-nc", "--nocache", action='store_true', help="ignore cache")
    parser.add_argument("-l", "--local", action='store_true', help="use local html")
    if (require_sheet):
        parser.add_argument("-s", "--sheets", nargs='*', help="RVTools Spreadsheet", required=True)
        parser.add_argument("-o", "--optimization", nargs='?', type=int, choices=range(1,50),  default=0, help="cpu optimization %", required=False)
    return parser.parse_args()