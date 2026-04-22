| Name                                 |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| restgdf/\_\_init\_\_.py              |       23 |        0 |        2 |        0 |    100% |           |
| restgdf/\_client/\_\_init\_\_.py     |        3 |        0 |        0 |        0 |    100% |           |
| restgdf/\_client/\_protocols.py      |        5 |        0 |        0 |        0 |    100% |           |
| restgdf/\_client/query\_options.py   |       56 |        0 |       12 |        0 |    100% |           |
| restgdf/\_client/request.py          |       10 |        0 |        4 |        0 |    100% |           |
| restgdf/\_compat.py                  |       22 |        0 |        2 |        0 |    100% |           |
| restgdf/\_config.py                  |      138 |        1 |       20 |        1 |     99% |       149 |
| restgdf/\_logging.py                 |       57 |        0 |       18 |        1 |     99% | 107-\>109 |
| restgdf/\_models/\_\_init\_\_.py     |        7 |        0 |        0 |        0 |    100% |           |
| restgdf/\_models/\_drift.py          |      148 |        2 |       66 |        3 |     98% |224, 244, 332-\>331 |
| restgdf/\_models/\_errors.py         |        3 |        0 |        0 |        0 |    100% |           |
| restgdf/\_models/\_settings.py       |       99 |        4 |       12 |        0 |     96% |283-284, 295-296 |
| restgdf/\_models/crawl.py            |       20 |        0 |        0 |        0 |    100% |           |
| restgdf/\_models/credentials.py      |       48 |        3 |        8 |        2 |     91% |109, 124-125 |
| restgdf/\_models/responses.py        |      175 |        5 |       56 |        3 |     97% |492-\>489, 518, 522-525 |
| restgdf/\_types.py                   |       12 |        0 |        2 |        0 |    100% |           |
| restgdf/adapters/\_\_init\_\_.py     |       14 |        0 |        2 |        0 |    100% |           |
| restgdf/adapters/dict.py             |       10 |        0 |        0 |        0 |    100% |           |
| restgdf/adapters/geopandas.py        |       13 |        0 |        0 |        0 |    100% |           |
| restgdf/adapters/pandas.py           |       11 |        0 |        0 |        0 |    100% |           |
| restgdf/adapters/stream.py           |       14 |        0 |        6 |        0 |    100% |           |
| restgdf/compat.py                    |       12 |        0 |        4 |        0 |    100% |           |
| restgdf/directory/\_\_init\_\_.py    |        2 |        0 |        0 |        0 |    100% |           |
| restgdf/directory/directory.py       |       53 |        0 |       16 |        1 |     99% |   67-\>76 |
| restgdf/errors.py                    |       77 |        0 |       16 |        1 |     99% | 255-\>257 |
| restgdf/featurelayer/\_\_init\_\_.py |        2 |        0 |        0 |        0 |    100% |           |
| restgdf/featurelayer/featurelayer.py |      187 |        1 |       48 |        4 |     98% |159, 267-\>273, 388-\>393, 430-\>435 |
| restgdf/resilience/\_\_init\_\_.py   |        9 |        0 |        0 |        0 |    100% |           |
| restgdf/resilience/\_errors.py       |       20 |        0 |        4 |        0 |    100% |           |
| restgdf/resilience/\_limiter.py      |       38 |        0 |        8 |        0 |    100% |           |
| restgdf/resilience/\_retry.py        |      103 |       19 |       20 |        4 |     78% |34, 37, 40, 43, 59, 63, 66, 74-76, 83-85, 158-\>161, 162, 169-170, 201-202, 223 |
| restgdf/telemetry/\_\_init\_\_.py    |        6 |        0 |        0 |        0 |    100% |           |
| restgdf/telemetry/\_correlation.py   |       12 |        2 |        2 |        0 |     86% |     18-19 |
| restgdf/telemetry/\_instrumentor.py  |       15 |        0 |        2 |        0 |    100% |           |
| restgdf/telemetry/\_spans.py         |       53 |        5 |       14 |        4 |     87% |51, 55, 56-\>58, 59, 91-92 |
| restgdf/utils/\_\_init\_\_.py        |       12 |        0 |        2 |        0 |    100% |           |
| restgdf/utils/\_concurrency.py       |       10 |        0 |        0 |        0 |    100% |           |
| restgdf/utils/\_deprecations.py      |       26 |        0 |        2 |        0 |    100% |           |
| restgdf/utils/\_http.py              |       30 |        0 |       10 |        0 |    100% |           |
| restgdf/utils/\_metadata.py          |       94 |        0 |       36 |        1 |     99% | 110-\>107 |
| restgdf/utils/\_optional.py          |       35 |        1 |        0 |        0 |     97% |        77 |
| restgdf/utils/\_pagination.py        |       30 |        0 |       10 |        0 |    100% |           |
| restgdf/utils/\_query.py             |       32 |        0 |        2 |        0 |    100% |           |
| restgdf/utils/\_stats.py             |       79 |        3 |       16 |        1 |     96% | 46-47, 95 |
| restgdf/utils/crawl.py               |       83 |        1 |       16 |        1 |     98% |        19 |
| restgdf/utils/getgdf.py              |      243 |        9 |       98 |        7 |     95% |56, 272, 280, 370, 374-378, 383-\>387, 385-\>387, 390-\>379, 640 |
| restgdf/utils/getinfo.py             |       58 |        0 |       10 |        0 |    100% |           |
| restgdf/utils/token.py               |      164 |        3 |       42 |        5 |     96% |181, 203-\>205, 221, 303, 372-\>374 |
| restgdf/utils/utils.py               |        9 |        0 |        0 |        0 |    100% |           |
| **TOTAL**                            | **2382** |   **59** |  **588** |   **39** | **96%** |           |
