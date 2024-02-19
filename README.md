<!-- PROJECT LOGO -->
<br />
<div align="center">
  <h3 align="center">RVTools Converter</h3>

  <p align="center">
    An script that allows you to produce a estimate based on an spreadsheet produced by RVtools.
    <br />
    <br />
    <a href="https://github.com/edsenabr/RVTools/issues">Report Bug</a>
    ·
    <a href="https://github.com/edsenabr/RVTools/issues">Request Feature</a>
  </p>
</div>

<!-- ABOUT THE PROJECT -->
## About The Project

Several times I needed to quickly produce an estimate on how much a customer infrastructure that is running on-premises on top of VMWare would cost on GCP. 

People usually adds up the cpus, memory and disk of all virtual machines, apply an optimization factor and then use an "average" vm to produce the estimate. 

Usually this approach is far from optimal, since some of those vms require an specific family or setup that the "average" approach won't cover. 

Because of that, over time I've created and improved this script that, in a nutshell:
* Fetches the updated pricing list for virtual machines
* Applies an optimization factor for the # of CPUs being provisioned by each VM (Optional)
* Finds the cheapest option for each VM, either using pre-defined shapes or exploring custom ones.
* Produces a spreadsheet with pricing a estimate, on both GCE and GCVE, for each region the user has requested.
<p>&nbsp;</p>

|:warning:|There are multiple considerations one should exercise with the produced estimate: This script looks for the cheapest option, it does not focus on performance and family specifics. For instance, licensing, sole-tenancy and over-commitment are not taken into account.<br/><br/>The best alternative always is running a detailed assessment with a proper tool to understand the specifics of the customer environment and produce a right-sized estimate.|
|-|-|


## Getting Started

This script is written in Python **`3`**, and it is recommended to create a virtual environment for installing its dependencies. Please refer to [requirements.txt](requirements.txt) to see the current dependencies, as those might evolve during time and I won't be updating this readme to address those changes.

There is no special instructions for installing this script. Just install Python, create a virtual environment, clone this repo and and install dependencies via PIP.


<!-- USAGE EXAMPLES -->
## Usage
A RVTools report could be a very large spreadsheet, but the script does not need all that info to produce the estimate. Only the following columns of the `vInfo` tab will be  used:

* VM
* CPUs 
* Memory
* Provisioned MiB
* OS according to the configuration file
* OS according to the VMware Tools

There are 3 executable scripts provided on this project:

|:memo:|you can invoke those executables with `--help` to figure out which options they support.|
|-|-|


* [price_loader.py](price_loader.py): This is a script that loads the price list. Run it only if you want to investigate if the scrapper is properly loading pricing data. It would produce an output similar to this:
  ```
  loaded 158 pre-defined types, 6 customizable families, 18 disk prices and 4 O.S. prices.
  ```
* [menu.py](menu.py): This script creates an interactive menu that allows you to select the cheapest shape for a desired configuration.
  ```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                                                                         │
  │  GCP PriceList Loader                                                   │
  │                                                                         │
  │  Prices loaded on YYYY-MM-DD for regions: southamerica-west1,           │
  │  southamerica-east1                                                     │
  │                                                                         │
  │                                                                         │
  │  Select an option:                                                      │
  │                                                                         │
  │                                                                         │
  │    1 - Select cheapest VM                                               │
  │    2 - List pre-defined types                                           │
  │    3 - List customizable families                                       │
  │    4 - List unit price for pre-defined types                            │
  │    5 - List disk prices                                                 │
  │    6 - List O.S. prices                                                 │
  │    7 - Exit                                                             │
  │                                                                         │
  │                                                                         │
  │  loaded 158 pre-defined types, 6 customizable families, 18 disk prices  │
  │  and 4 O.S. prices.                                                     │
  │                                                                         │
  │                                                                         │
  └─────────────────────────────────────────────────────────────────────────┘
  >> 
  ```
* [estimate_rvtools.py](estimate_rvtools.py): This is the main script you want to execute for producing your estimate. It accepts one or more rvtools spreadsheets as input and produces a single output file named `estimated-rvtools-DATE-TIME.xlsx`, with one tab per input file named after each input file. Here's a sample output of an execution:
  ```
  WARNING! using cache file 'price_loader.json' from YYYY-MM-DD
          loaded 158 pre-defined types, 6 customizable families, 18 disk prices and 4 O.S. prices.
          use -nc to avoid caching or delete the file
  Input.xlsx: 100%|█████████████████████████████████████████| 3806/3806 [00:02<00:00, 1428.56it/s]
  saving output file...
  ...done.
  ```
<!-- CONTRIBUTING -->
## Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".
Don't forget to give the project a star! Thanks again!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request


<!-- LICENSE -->
## License

Distributed under the MIT License. See [LICENSE.txt](LICENSE.txt) for more information. 

README inspired by the [BestREADME Template](https://github.com/othneildrew/Best-README-Template/)