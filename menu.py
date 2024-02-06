#!/bin/bash
"exec" "$(dirname $0)/env/bin/python3" "$0" "$@"


from datetime import datetime
from pricing import PriceList, parse_args
from consolemenu import *
from consolemenu.items import *
from consolemenu.prompt_utils import PromptUtils, InputResult
from tabulate import tabulate

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

    if (memory < 1024):
        memory *= 1024

    print_list([price_list.select_price(commit, cpu, memory, region, verbose=True)])
    
    return (cpu, memory)

def print_list(list):
    print(tabulate(list, headers="keys"), '\n')
    utils.enter_to_continue()


def print_selection(commit, region):
    print(commit)
    utils.enter_to_continue()

def build_menu():
    when = datetime.fromtimestamp(price_list.last_update).strftime("%Y-%m-%d")
    menu = ConsoleMenu("GCP PriceList Loader", "Loaded on {when} prices for regions: ".format(when=when) + ', '.join(args.regions), epilogue_text=price_list.count(), prologue_text="Select an option:")

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
        FunctionItem("List O.S. prices", print_list, args=[[price_list.lists['images']]])
    )
    return menu


if (__name__=="__main__"):
    args = parse_args()
    price_list = PriceList(args.regions, args.period, args.nocache, args.local)
    menu = build_menu()
    utils = PromptUtils(menu.screen)


    while True:
        menu.show()
        if menu.is_selected_item_exit:
            break
        else:
            print(menu.selected_item)