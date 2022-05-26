#!/usr/bin/env python3
from price_loader import PriceList
import argparse
from consolemenu import *
from consolemenu.items import *
from consolemenu.prompt_utils import PromptUtils, BaseValidator, InputResult
from tabulate import tabulate
from timebudget import timebudget
timebudget.set_quiet()  # don't show measurements as they happen

def read_float_value(label):
    try:
        return float(input("%s:\t\t" % label))
    except ValueError:
        print ("Invalid value, enter a numeric data in the form of 00[.0]")
        return read_float_value(label)
    except KeyboardInterrupt:
        return None



def select_best_vm(commit, region):
    cpu = read_float_value("cpu")
    if (cpu is None):
        return

    memory = read_float_value("memory")
    if (memory is None):
        return

    print_list([price_list.select_price(commit, cpu, memory, region, verbose=True)])
    timebudget.report()
    
    return (cpu, memory)

def print_list(list):
    print(tabulate(list, headers="keys"), '\n')
    utils.enter_to_continue()


def get_parser(h):
    parser = argparse.ArgumentParser(add_help=h)
    parser.add_argument("-r", "--regions", nargs='*', help="regions to be loaded", required=True)
    return parser


def print_selection(commit, region):
    print(commit)
    utils.enter_to_continue()

@timebudget    
def build_menu():
    menu = ConsoleMenu("GCP PriceList Loader", "Loaded prices for regions: " + ', '.join(args.regions), epilogue_text=price_list.count(), prologue_text="Select an option:")

    region_menu = ConsoleMenu("Choose a region", clear_screen=False)
    for region in args.regions:

        commit_menu = ConsoleMenu("Select Commit Type")
        commit_menu.append_item(
            FunctionItem("On Demand", select_best_vm, args=['od', region], should_exit=True)
        )
        commit_menu.append_item(
            FunctionItem("CUD", select_best_vm, args=['cud1y', region], should_exit=True)
        )
        submenu_item = SubmenuItem(region, commit_menu, region_menu, should_exit=True)
        region_menu.append_item(submenu_item)

    region_item = SubmenuItem("Select best VM", region_menu, menu)
    menu.append_item(region_item)

    menu.append_item(
        FunctionItem("List pre-defined types", print_list, args=[price_list.lists['predefined']])
    )
    menu.append_item(
        FunctionItem("List custom types", print_list, args=[price_list.lists['custom']])
    )
    menu.append_item(
        FunctionItem("List standard prices", print_list, args=[price_list.lists['standard']])
    )
    menu.append_item(
        FunctionItem("List disk prices", print_list, args=[price_list.lists['disk']])
    )
    menu.append_item(
        FunctionItem("List O.S. prices", print_list, args=[[price_list.images]])
    )
    return menu


if (__name__=="__main__"):

    p = get_parser(h=True)
    args = p.parse_args()
    price_list = PriceList(args.regions, 'monthly')
    menu = build_menu()
    utils = PromptUtils(menu.screen)


    while True:
        menu.show()
        if menu.is_selected_item_exit:
            break
        else:
            print(menu.selected_item)
    timebudget.report('load price list')