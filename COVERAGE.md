| Name                                   |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| restgdf/\_\_init\_\_.py                |       23 |        0 |        2 |        0 |    100% |           |
| restgdf/\_client/\_\_init\_\_.py       |        3 |        0 |        0 |        0 |    100% |           |
| restgdf/\_client/\_protocols.py        |        5 |        0 |        0 |        0 |    100% |           |
| restgdf/\_client/query\_options.py     |       56 |        0 |       12 |        0 |    100% |           |
| restgdf/\_client/request.py            |       10 |        0 |        4 |        0 |    100% |           |
| restgdf/\_compat.py                    |       22 |        0 |        2 |        0 |    100% |           |
| restgdf/\_config.py                    |      139 |        1 |       20 |        1 |     99% |       176 |
| restgdf/\_logging.py                   |       59 |        0 |       18 |        1 |     99% | 107-\>109 |
| restgdf/\_models/\_\_init\_\_.py       |        7 |        0 |        0 |        0 |    100% |           |
| restgdf/\_models/\_drift.py            |      145 |        2 |       66 |        3 |     98% |221, 241, 329-\>328 |
| restgdf/\_models/\_errors.py           |        3 |        0 |        0 |        0 |    100% |           |
| restgdf/\_models/\_settings.py         |      100 |        4 |       12 |        0 |     96% |289-290, 301-302 |
| restgdf/\_models/crawl.py              |       20 |        0 |        0 |        0 |    100% |           |
| restgdf/\_models/credentials.py        |       53 |        0 |        8 |        0 |    100% |           |
| restgdf/\_models/responses.py          |      175 |        5 |       56 |        3 |     97% |492-\>489, 518, 522-525 |
| restgdf/\_types.py                     |       12 |        0 |        2 |        0 |    100% |           |
| restgdf/adapters/\_\_init\_\_.py       |       14 |        0 |        2 |        0 |    100% |           |
| restgdf/adapters/dict.py               |       10 |        0 |        0 |        0 |    100% |           |
| restgdf/adapters/geopandas.py          |       13 |        0 |        0 |        0 |    100% |           |
| restgdf/adapters/pandas.py             |       40 |        1 |       18 |        2 |     95% |33, 106-\>94 |
| restgdf/adapters/stream.py             |       14 |        0 |        6 |        0 |    100% |           |
| restgdf/compat.py                      |       12 |        0 |        4 |        0 |    100% |           |
| restgdf/directory/\_\_init\_\_.py      |        2 |        0 |        0 |        0 |    100% |           |
| restgdf/directory/directory.py         |       51 |        0 |       16 |        1 |     99% | 133-\>142 |
| restgdf/errors.py                      |       78 |        0 |       16 |        1 |     99% | 255-\>257 |
| restgdf/featurelayer/\_\_init\_\_.py   |        2 |        0 |        0 |        0 |    100% |           |
| restgdf/featurelayer/featurelayer.py   |      193 |        1 |       52 |        4 |     98% |206, 364-\>370, 485-\>490, 553-\>558 |
| restgdf/resilience/\_\_init\_\_.py     |       10 |        0 |        0 |        0 |    100% |           |
| restgdf/resilience/\_bounded\_retry.py |       19 |        0 |        0 |        0 |    100% |           |
| restgdf/resilience/\_errors.py         |       21 |        0 |        4 |        0 |    100% |           |
| restgdf/resilience/\_limiter.py        |       38 |        0 |        8 |        0 |    100% |           |
| restgdf/resilience/\_retry.py          |      120 |        0 |       26 |        2 |     99% |134-\>exit, 177-\>180 |
| restgdf/telemetry/\_\_init\_\_.py      |        6 |        0 |        0 |        0 |    100% |           |
| restgdf/telemetry/\_correlation.py     |       12 |        0 |        2 |        0 |    100% |           |
| restgdf/telemetry/\_instrumentor.py    |       15 |        0 |        2 |        0 |    100% |           |
| restgdf/telemetry/\_spans.py           |       53 |        0 |       14 |        0 |    100% |           |
| restgdf/utils/\_\_init\_\_.py          |       12 |        0 |        2 |        0 |    100% |           |
| restgdf/utils/\_concurrency.py         |       10 |        0 |        0 |        0 |    100% |           |
| restgdf/utils/\_deprecations.py        |       27 |        0 |        2 |        0 |    100% |           |
| restgdf/utils/\_geometry.py            |      100 |        0 |       64 |        0 |    100% |           |
| restgdf/utils/\_http.py                |       67 |        0 |       24 |        0 |    100% |           |
| restgdf/utils/\_metadata.py            |       94 |        0 |       36 |        1 |     99% | 110-\>107 |
| restgdf/utils/\_optional.py            |       35 |        1 |        0 |        0 |     97% |        77 |
| restgdf/utils/\_pagination.py          |       30 |        0 |       10 |        0 |    100% |           |
| restgdf/utils/\_query.py               |       31 |        0 |        2 |        0 |    100% |           |
| restgdf/utils/\_stats.py               |       78 |        3 |       16 |        1 |     96% | 45-46, 95 |
| restgdf/utils/crawl.py                 |       82 |        1 |       16 |        1 |     98% |        25 |
| restgdf/utils/getgdf.py                |      418 |        7 |      182 |       11 |     97% |68, 155, 162-\>161, 224-225, 497, 507-\>506, 634-\>636, 639-\>628, 990, 1023, 1026-\>1044, 1030-\>1032, 1032-\>1026 |
| restgdf/utils/getinfo.py               |       65 |        0 |       12 |        0 |    100% |           |
| restgdf/utils/token.py                 |      209 |        3 |       56 |        4 |     97% |230, 253, 443, 627-\>exit |
| restgdf/utils/utils.py                 |        8 |        0 |        0 |        0 |    100% |           |
| **TOTAL**                              | **2821** |   **29** |  **794** |   **36** | **98%** |           |
