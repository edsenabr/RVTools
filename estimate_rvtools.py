#!/usr/bin/python3
import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import enum
from heapq import merge
from locale import currency
from textwrap import fill
from price_loader import PriceList, Incrementor
from util import CellFormat
from queue import Queue
import openpyxl
import operator
from tqdm import tqdm
from timebudget import timebudget
timebudget.set_quiet()  # don't show measurements as they happen
timebudget.report_at_exit()  # Generate report when the program exits

commit_colors = {
    "OD": "FFD8CE",
    "1Y":"FFF5CE",
    "3Y": "DDE8CB"
}


def get_parser(h):
    parser = argparse.ArgumentParser(add_help=h)
    parser.add_argument("-r", "--regions", nargs='*', help="region to be loaded", required=False)
    parser.add_argument("-s", "--sheets", nargs='*', help="RVTools Spreadsheet", required=False)
    return parser

def process_row(sheet, row_index, row, regions):
    [vm, cpus, memory, disk, os_conf, os_tools] = operator.itemgetter(0, 14, 15, 38, 71, 72)(row)
    disk = max(10, disk/1024)

    os = os_conf or os_tools
    os_price = None
    if isinstance(os, str):
        os_price = price_list.get_os_price(os, cpus)


    color = 'EEEEEE' if not (row_index % 2) else None

    std = CellFormat(sheet).color(color)
    curr = CellFormat(sheet).color(color).currency()
    gb = CellFormat(sheet).color(color).gb()

    data=[
        std.value(vm), 
        std.value(cpus), 
        gb.value(memory/1024), 
        gb.value(disk), 
        std.value(os)
    ]

    for region in regions:
        od = price_list.select_price("od", cpus, memory, region)
        cud = price_list.select_price("cud1y", cpus, memory, region)
        data.extend([
            std.value( od["name"]),
            curr.value( od["od"]),
            std.value( cud["name"]),
            curr.value( cud["cud1y"]),
            std.value( cud["name"]),
            curr.value( cud["cud3y"]),
            curr.value( os_price),
            curr.value( price_list.select_disk_price("standard", region)*disk),
            curr.value( price_list.select_disk_price("balanced", region)*disk),
            curr.value( price_list.select_disk_price("ssd", region)*disk),
        ])
    sheet.append(data)
    return data

initial_row_offset=1
initial_column_offset=1
spacer=3

def add_gcve_info_to_summary(summary, sheet_name, regions_qtty, book_index):
    row_offset = get_gcve_offset(regions_qtty) +  book_index
    data = [
        sheet_name,
        "=SUM('{path}'!B:B)".format(path=sheet_name),
        CellFormat(summary).tb().value("=SUM('{path}'!C:C)/1024".format(path=sheet_name)),
        CellFormat(summary).tb().value("=SUM('{path}'!D:D)/1024".format(path=sheet_name)),
        '=ROUNDUP(max(INDIRECT(ADDRESS(ROW(),2))/72,INDIRECT(ADDRESS(ROW(),3))/768,INDIRECT(ADDRESS(ROW(),4))/(19.2)))'
    ]
    write_row_to(summary, initial_column_offset, row_offset, data)


def add_book_to_summary(summary, book_index, book_name, region_index, region_name, regions_qtty):

    gcve_price = price_list.get_gcve_price(region_name)
    if gcve_price is None:
        gcve_price = {"od": "NA()", "cud1y": "NA()", "cud3y":"NA()"}
    
    book_region_start_colum=5+(10*region_index)
    region_offset = get_region_offset(region_index)

    commits_name={
        1: "OD",
        3: "1Y",
        5: "3Y"
    }

    commits_column={
        1: "od",
        3: "cud1y",
        5: "cud3y"
    }

    gcve_offset = get_gcve_offset(regions_qtty) +  book_index
    for row_index, first in enumerate([1,3,5]):
        summary_row = [commits_name[first]]
        for third in [9,8,7]:
            summary_row.append(
            "=SUM('{path}'!{first}:{first}, '{path}'!{second}:{second}, '{path}'!{third}:{third})".format(
                first=to_letter(book_region_start_colum+first),
                second=to_letter(book_region_start_colum+6),
                third=to_letter(book_region_start_colum+third),
                path=book_name
            ))
        summary_row.append(
            '''=E{gcve_offset}*{price}'''.format(gcve_offset=gcve_offset, price=gcve_price[commits_column[first]])
        )
        book_offset = book_index*3
        row_offset = region_offset + book_offset + row_index
        write_row_to(summary, initial_column_offset+1, row_offset, summary_row, CellFormat().currency().color(commit_colors[commits_name[first]]))
    
    merge_offset=region_offset + (book_index*3)
    region_color = ['DEE7E5', 'DEDCE6', 'F6F9D4'][region_index % 3]
    write_header_cell(summary, start_row=merge_offset, start_column=initial_column_offset, end_row=merge_offset+2, end_column=initial_column_offset, value=book_name, color=region_color)
    
    region_header_offset=get_region_offset(region_index, header=True)

    write_header_cell(summary, start_row=region_header_offset, start_column=initial_column_offset, end_row=region_header_offset+1, end_column=initial_column_offset, value=region_name, color=region_color)
    write_header_cell(summary, start_row=region_header_offset, start_column=initial_column_offset+1, end_row=region_header_offset+1, end_column=initial_column_offset+1, value='Commit', color=region_color)
    write_header_cell(summary, start_row=region_header_offset, start_column=initial_column_offset+2, end_row=region_header_offset, end_column=initial_column_offset+4, value="GCE w/ Disk Type", color=region_color)
    write_header_cell(summary, start_row=region_header_offset, start_column=initial_column_offset+5, end_row=region_header_offset+1, end_column=initial_column_offset+5, value="GCVE", color=region_color)

    write_row_to(summary, initial_column_offset+2, region_header_offset+1, ["SSD", "Balanced", "Standard"], CellFormat().header(region_color))

def get_gcve_offset(regions_qtty, header=False):
    return initial_row_offset + (regions_qtty * (11 + spacer)) + (2 if not header else 0)

def get_region_offset(region_index, header=False):
    return initial_row_offset + (region_index * (11 + spacer)) + (2 if not header else 0)

def format_summary(summary, books, regions_qtty):
    for region_index in range(0, regions_qtty):
        region_offset = get_region_offset(region_index, True)
        summary.merge_cells(start_row=region_offset, start_column=initial_column_offset, end_row=region_offset, end_column=initial_column_offset+3)  

def update_summary(summary, region_index, books, regions_qtty):
    region_offset = get_region_offset(region_index)
    first_region_row = region_offset + 6
    first_sum_row = region_offset
    last_sum_row = region_offset + 5
    for row_offset, commit in enumerate(['OD', '1Y', '3Y']):
        summary_row = [commit]
        for column in ['C', 'D', 'E', 'F']:
            summary_row.append(
                '''=SUMPRODUCT((B{first}:B{last}="{commit}")*({column}{first}:{column}{last}))'''.format(first=first_sum_row, last=last_sum_row, commit=commit, column=column),
            )
        write_row_to(summary, initial_column_offset+1, first_region_row + row_offset, summary_row, CellFormat().currency().color(commit_colors[commit]))
    region_color = ['DEE7E5', 'DEDCE6', 'F6F9D4'][region_index % 3]
    write_header_cell(summary, start_row=first_region_row, start_column=initial_column_offset, end_row=first_region_row+2, end_column=initial_column_offset, value="TOTAL", color=region_color)

    summary.column_dimensions['A'].width=30
    summary.column_dimensions['B'].width=8
    for colum_label in ['C', 'D', 'E', 'F']:
        summary.column_dimensions[colum_label].width=15

def update_gcve_summary(summary, regions_qtty, books_qtty):
    write_header_cell(summary, start_row=get_gcve_offset(regions_qtty, header=True), start_column=initial_column_offset, end_row=get_gcve_offset(regions_qtty, header=True), end_column=initial_column_offset+4, value="GCVE", color='FFDBB6')
    write_row_to(summary, initial_column_offset, get_gcve_offset(regions_qtty, header=True)+1, ['RVTools file', 'vCPUS', 'Memory', 'Disk', 'Hosts'], CellFormat().header('FFDBB6'))
    if books_qtty > 1:
        first = get_gcve_offset(regions_qtty)
        last = get_gcve_offset(regions_qtty) + books_qtty - 1
        summary.append([
            CellFormat(summary).header('FFDBB6').value('TOTAL'),
            CellFormat(summary).color('FFDBB6').value('''=SUM(B{first}:B{last})'''.format(first=first, last=last)),
            CellFormat(summary).color('FFDBB6').tb().value('''=SUM(C{first}:C{last})'''.format(first=first, last=last)),
            CellFormat(summary).color('FFDBB6').tb().value('''=SUM(D{first}:D{last})'''.format(first=first, last=last)),
            CellFormat(summary).color('FFDBB6').value('''=SUM(E{first}:E{last})'''.format(first=first, last=last))
        ])


def to_letter(number):
    return chr(ord('@')+(number+1))

def write_row_to(sheet, column_offset, row, data, format=None):
    for columm, value in enumerate(data):
        cell = sheet.cell(row, column_offset+columm, value) 
        if not format is None:
            format.apply(cell)
    
def write_book_header(sheet, regions):
    write_header_cell(sheet, start_row=1, start_column=1, end_row=4, end_column=5, value='INPUT', color='DEE6EF')
    write_header_cell(sheet, start_row=1, start_column=6, end_row=1, end_column=5+(len(regions)*10), value='OUTPUT', color='DEE6EF')
    write_row_to(sheet, 1, 5, ['VM', 'CPUS', 'Memory', 'Disk', 'OS'])
    for region_index, region_name in enumerate(regions):
        write_book_region_header(sheet, region_index, region_name)

def write_header_cell(sheet, start_row, start_column, end_row=None, end_column=None, value='', color=None):
    if not end_column is None and not end_row is None:
        sheet.merge_cells(start_row=start_row, start_column=start_column, end_row=end_row, end_column=end_column)
    thin = openpyxl.styles.Side(border_style="thin", color="000000")
    cell = sheet.cell(column=start_column, row=start_row, value=value)
    cell.alignment = openpyxl.styles.alignment.Alignment(horizontal="center", vertical="center")
    if not color is None:
        cell.fill = openpyxl.styles.PatternFill("solid", fgColor=color)
    cell.font = openpyxl.styles.Font(bold=True)
    cell.border = openpyxl.styles.Border(top=thin, left=thin, right=thin, bottom=thin)

def write_book_region_header(sheet, region_index, region_name):
    header_offset_column = 6 + (region_index*10)
    region_color = ['DEE7E5', 'DEDCE6', 'F6F9D4'][region_index % 3]
    
    write_header_cell(sheet, start_row=2, start_column=header_offset_column, end_row=2, end_column=header_offset_column+9, value=region_name, color=region_color)
    write_header_cell(sheet, start_row=3, start_column=header_offset_column, end_row=3, end_column=header_offset_column+5, value="COMPUTE", color=region_color)
    write_header_cell(sheet, start_row=3, start_column=header_offset_column+6, end_row=4, end_column=header_offset_column+6, value="O.S.", color=region_color)
    write_header_cell(sheet, start_row=3, start_column=header_offset_column+7, end_row=4, end_column=header_offset_column+9, value="Disk", color=region_color)
    write_header_cell(sheet, start_row=4, start_column=header_offset_column, end_row=4, end_column=header_offset_column+1, value="ON DEMAND", color='FFD8CE')
    write_header_cell(sheet, start_row=4, start_column=header_offset_column+2, end_row=4, end_column=header_offset_column+3, value="1 YEAR COMMIT", color='FFF5CE')
    write_header_cell(sheet, start_row=4, start_column=header_offset_column+4, end_row=4, end_column=header_offset_column+5, value="3 YEARS COMMIT", color='DDE8CB')

    write_row_to(sheet, header_offset_column, 5, [
        'Family', 
        'Price', 
        'Family', 
        'Price', 
        'Family', 
        'Price', 
        'License',
        'Standard', 
        'Balanced', 
        'SSD'
    ], CellFormat().bold())

def is_currency(index):
    label = openpyxl.utils.get_column_letter(index)
    if index < 6:
        return False
    if (index -5) % 10 not in [1, 3, 5]:
        return True

    return False

def fit_columns(sheet, regions_qtty):
    for index, column in enumerate(sheet.iter_cols(), 1):
        label = openpyxl.utils.get_column_letter(index)
        if index in [2,3,4]:
            sheet.column_dimensions[label].width= 10
        elif is_currency(index):
            sheet.column_dimensions[label].width= 8
        else:
            length = max(len(str(cell.value))  for cell in column)
            sheet.column_dimensions[label].width = length

@timebudget
def read_books(books, regions):
    books_qtty= len(books)
    regions_qtty= len(regions)
    output = openpyxl.Workbook()
    summary = output.active
    summary.title="Summary"
    for book_index, book_name in enumerate(books):
        book = openpyxl.load_workbook(book_name, read_only=True, data_only=True)
        sheet = output.create_sheet(book_name)
        write_book_header(sheet, regions)
        for row_index, row in enumerate(book['vInfo'].iter_rows(min_row=2, min_col=1, max_col=74, values_only=True)):
            process_row(sheet, row_index, row, regions)
        for region_index, region_name in enumerate(regions):
            add_book_to_summary(summary, book_index, book_name, region_index, region_name, regions_qtty)

        update_summary(summary, book_index, books_qtty, regions_qtty)
        add_gcve_info_to_summary(summary, book_name, regions_qtty, book_index)
        fit_columns(sheet, regions_qtty)

    update_gcve_summary(summary, regions_qtty, books_qtty)
    output.save(filename = 'estimated-rvtools.xlsx')
    output.close()

if (__name__=="__main__"):
    with timebudget("TOTAL TIME"):
        p = get_parser(h=True)
        args = p.parse_args()
        price_list = PriceList(args.regions, 'monthly')
        read_books(args.sheets, args.regions)