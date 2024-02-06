#!/bin/bash
"exec" "$(dirname $0)/env/bin/python3" "$0" "$@"

from pricing import PriceList, parse_args

if (__name__=="__main__"):
    args = parse_args()
    price_list = PriceList(args.regions, args.period, args.nocache, args.local)
    print(price_list.count())    
    pass