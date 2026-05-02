| Name                                   |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| restgdf/\_\_init\_\_.py                |       23 |        0 |        2 |        0 |    100% |           |
| restgdf/\_client/\_\_init\_\_.py       |        3 |        0 |        0 |        0 |    100% |           |
| restgdf/\_client/\_protocols.py        |        5 |        0 |        0 |        0 |    100% |           |
| restgdf/\_client/query\_options.py     |       56 |        0 |       12 |        0 |    100% |           |
| restgdf/\_client/request.py            |       10 |        0 |        4 |        0 |    100% |           |
| restgdf/\_compat.py                    |       22 |        0 |        2 |        0 |    100% |           |
| restgdf/\_config.py                    |      138 |        1 |       20 |        1 |     99% |       149 |
| restgdf/\_logging.py                   |       57 |        0 |       18 |        1 |     99% | 107-\>109 |
| restgdf/\_models/\_\_init\_\_.py       |        7 |        0 |        0 |        0 |    100% |           |
| restgdf/\_models/\_drift.py            |      148 |        2 |       66 |        3 |     98% |224, 244, 332-\>331 |
| restgdf/\_models/\_errors.py           |        3 |        0 |        0 |        0 |    100% |           |
| restgdf/\_models/\_settings.py         |       99 |        4 |       12 |        0 |     96% |283-284, 295-296 |
| restgdf/\_models/crawl.py              |       20 |        0 |        0 |        0 |    100% |           |
| restgdf/\_models/credentials.py        |       48 |        0 |        8 |        0 |    100% |           |
| restgdf/\_models/responses.py          |      175 |        5 |       56 |        3 |     97% |492-\>489, 518, 522-525 |
| restgdf/\_types.py                     |       12 |        0 |        2 |        0 |    100% |           |
| restgdf/adapters/\_\_init\_\_.py       |       14 |        0 |        2 |        0 |    100% |           |
| restgdf/adapters/dict.py               |       10 |        0 |        0 |        0 |    100% |           |
| restgdf/adapters/geopandas.py          |       13 |        0 |        0 |        0 |    100% |           |
| restgdf/adapters/pandas.py             |       40 |        1 |       18 |        2 |     95% |33, 106-\>94 |
| restgdf/adapters/stream.py             |       14 |        0 |        6 |        0 |    100% |           |
| restgdf/compat.py                      |       12 |        0 |        4 |        0 |    100% |           |
| restgdf/directory/\_\_init\_\_.py      |        2 |        0 |        0 |        0 |    100% |           |
| restgdf/directory/directory.py         |       52 |        0 |       16 |        1 |     99% |   66-\>75 |
| restgdf/errors.py                      |       78 |        0 |       16 |        1 |     99% | 255-\>257 |
| restgdf/featurelayer/\_\_init\_\_.py   |        2 |        0 |        0 |        0 |    100% |           |
| restgdf/featurelayer/featurelayer.py   |      190 |        1 |       50 |        4 |     98% |158, 266-\>272, 387-\>392, 455-\>460 |
| restgdf/resilience/\_\_init\_\_.py     |       10 |        0 |        0 |        0 |    100% |           |
| restgdf/resilience/\_bounded\_retry.py |       18 |        0 |        0 |        0 |    100% |           |
| restgdf/resilience/\_errors.py         |       20 |        0 |        4 |        0 |    100% |           |
| restgdf/resilience/\_limiter.py        |       38 |        0 |        8 |        0 |    100% |           |
| restgdf/resilience/\_retry.py          |      120 |        2 |       26 |        3 |     97% |134-\>exit, 177-\>180, 260-261 |
| restgdf/telemetry/\_\_init\_\_.py      |        6 |        0 |        0 |        0 |    100% |           |
| restgdf/telemetry/\_correlation.py     |       12 |        0 |        2 |        0 |    100% |           |
| restgdf/telemetry/\_instrumentor.py    |       15 |        0 |        2 |        0 |    100% |           |
| restgdf/telemetry/\_spans.py           |       53 |        0 |       14 |        0 |    100% |           |
| restgdf/utils/\_\_init\_\_.py          |       12 |        0 |        2 |        0 |    100% |           |
| restgdf/utils/\_concurrency.py         |       10 |        0 |        0 |        0 |    100% |           |
| restgdf/utils/\_deprecations.py        |       26 |        0 |        2 |        0 |    100% |           |
| restgdf/utils/\_http.py                |       69 |        2 |       24 |        0 |     98% |   177-178 |
| restgdf/utils/\_metadata.py            |       94 |        0 |       36 |        1 |     99% | 110-\>107 |
| restgdf/utils/\_optional.py            |       35 |        1 |        0 |        0 |     97% |        77 |
| restgdf/utils/\_pagination.py          |       30 |        0 |       10 |        0 |    100% |           |
| restgdf/utils/\_query.py               |       31 |        0 |        2 |        0 |    100% |           |
| restgdf/utils/\_stats.py               |       78 |        3 |       16 |        1 |     96% | 45-46, 95 |
| restgdf/utils/crawl.py                 |       82 |        1 |       16 |        1 |     98% |        18 |
| restgdf/utils/getgdf.py                |      388 |        7 |      170 |       14 |     96% |63, 150, 157-\>156, 219-220, 432, 442-\>441, 552-\>554, 557-\>546, 796-\>794, 810-\>808, 839, 855-\>854, 872, 875-\>893, 879-\>881, 881-\>875 |
| restgdf/utils/getinfo.py               |       64 |        0 |       12 |        0 |    100% |           |
| restgdf/utils/token.py                 |      170 |        2 |       44 |        4 |     97% |181, 303, 372-\>374, 451-\>exit |
| restgdf/utils/utils.py                 |        9 |        0 |        0 |        0 |    100% |           |
| **TOTAL**                              | **2643** |   **32** |  **704** |   **40** | **98%** |           |
