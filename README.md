# Control Node

Orchestrates recording across Pi Zero camera nodes.

## Setup

Collecting fastapi==0.115.12 (from -r requirements.txt (line 1))
  Downloading fastapi-0.115.12-py3-none-any.whl.metadata (27 kB)
Collecting httptools==0.6.4 (from -r requirements.txt (line 2))
  Downloading httptools-0.6.4.tar.gz (240 kB)
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Getting requirements to build wheel: started
  Getting requirements to build wheel: finished with status 'done'
  Preparing metadata (pyproject.toml): started
  Preparing metadata (pyproject.toml): finished with status 'done'
Collecting paho-mqtt==2.1.0 (from -r requirements.txt (line 3))
  Using cached paho_mqtt-2.1.0-py3-none-any.whl.metadata (23 kB)
Collecting psutil==7.2.2 (from -r requirements.txt (line 4))
  Using cached psutil-7.2.2-cp36-abi3-macosx_11_0_arm64.whl.metadata (22 kB)
Collecting python-dotenv==1.2.2 (from -r requirements.txt (line 5))
  Downloading python_dotenv-1.2.2-py3-none-any.whl.metadata (27 kB)
Collecting uvicorn==0.34.2 (from -r requirements.txt (line 6))
  Downloading uvicorn-0.34.2-py3-none-any.whl.metadata (6.5 kB)
Collecting uvloop==0.21.0 (from -r requirements.txt (line 7))
  Downloading uvloop-0.21.0.tar.gz (2.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.5/2.5 MB 4.1 MB/s  0:00:00
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Getting requirements to build wheel: started
  Getting requirements to build wheel: finished with status 'done'
  Preparing metadata (pyproject.toml): started
  Preparing metadata (pyproject.toml): finished with status 'done'
Collecting starlette<0.47.0,>=0.40.0 (from fastapi==0.115.12->-r requirements.txt (line 1))
  Downloading starlette-0.46.2-py3-none-any.whl.metadata (6.2 kB)
Collecting pydantic!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0,>=1.7.4 (from fastapi==0.115.12->-r requirements.txt (line 1))
  Using cached pydantic-2.12.5-py3-none-any.whl.metadata (90 kB)
Collecting typing-extensions>=4.8.0 (from fastapi==0.115.12->-r requirements.txt (line 1))
  Using cached typing_extensions-4.15.0-py3-none-any.whl.metadata (3.3 kB)
Collecting click>=7.0 (from uvicorn==0.34.2->-r requirements.txt (line 6))
  Using cached click-8.3.1-py3-none-any.whl.metadata (2.6 kB)
Collecting h11>=0.8 (from uvicorn==0.34.2->-r requirements.txt (line 6))
  Using cached h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
Collecting annotated-types>=0.6.0 (from pydantic!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0,>=1.7.4->fastapi==0.115.12->-r requirements.txt (line 1))
  Using cached annotated_types-0.7.0-py3-none-any.whl.metadata (15 kB)
Collecting pydantic-core==2.41.5 (from pydantic!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0,>=1.7.4->fastapi==0.115.12->-r requirements.txt (line 1))
  Downloading pydantic_core-2.41.5-cp314-cp314-macosx_11_0_arm64.whl.metadata (7.3 kB)
Collecting typing-inspection>=0.4.2 (from pydantic!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0,>=1.7.4->fastapi==0.115.12->-r requirements.txt (line 1))
  Using cached typing_inspection-0.4.2-py3-none-any.whl.metadata (2.6 kB)
Collecting anyio<5,>=3.6.2 (from starlette<0.47.0,>=0.40.0->fastapi==0.115.12->-r requirements.txt (line 1))
  Using cached anyio-4.13.0-py3-none-any.whl.metadata (4.5 kB)
Collecting idna>=2.8 (from anyio<5,>=3.6.2->starlette<0.47.0,>=0.40.0->fastapi==0.115.12->-r requirements.txt (line 1))
  Using cached idna-3.11-py3-none-any.whl.metadata (8.4 kB)
Downloading fastapi-0.115.12-py3-none-any.whl (95 kB)
Using cached paho_mqtt-2.1.0-py3-none-any.whl (67 kB)
Using cached psutil-7.2.2-cp36-abi3-macosx_11_0_arm64.whl (129 kB)
Downloading python_dotenv-1.2.2-py3-none-any.whl (22 kB)
Downloading uvicorn-0.34.2-py3-none-any.whl (62 kB)
Using cached pydantic-2.12.5-py3-none-any.whl (463 kB)
Downloading pydantic_core-2.41.5-cp314-cp314-macosx_11_0_arm64.whl (1.9 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.9/1.9 MB 4.6 MB/s  0:00:00
Downloading starlette-0.46.2-py3-none-any.whl (72 kB)
Using cached anyio-4.13.0-py3-none-any.whl (114 kB)
Using cached annotated_types-0.7.0-py3-none-any.whl (13 kB)
Using cached click-8.3.1-py3-none-any.whl (108 kB)
Using cached h11-0.16.0-py3-none-any.whl (37 kB)
Using cached idna-3.11-py3-none-any.whl (71 kB)
Using cached typing_extensions-4.15.0-py3-none-any.whl (44 kB)
Using cached typing_inspection-0.4.2-py3-none-any.whl (14 kB)
Building wheels for collected packages: httptools, uvloop
  Building wheel for httptools (pyproject.toml): started
  Building wheel for httptools (pyproject.toml): finished with status 'done'
  Created wheel for httptools: filename=httptools-0.6.4-cp314-cp314-macosx_15_0_arm64.whl size=102142 sha256=50fcb25172fed1853f17aa5ee1b3fc86d17a1750833344df020a96ffbfbdb307
  Stored in directory: /Users/drogba/Library/Caches/pip/wheels/d7/d8/60/7ab2629d1e58538a236613cc9032465f79319fca58366b2720
  Building wheel for uvloop (pyproject.toml): started
  Building wheel for uvloop (pyproject.toml): finished with status 'done'
  Created wheel for uvloop: filename=uvloop-0.21.0-cp314-cp314-macosx_15_0_arm64.whl size=773324 sha256=4e4f21806f92b919a5300e8e57fa190e3679b59104ed07ba2a2b512d1a26ee27
  Stored in directory: /Users/drogba/Library/Caches/pip/wheels/95/ea/4e/a37809f9e9ef443c9a0be8ed1a3ae836da8b51045de9f38b1d
Successfully built httptools uvloop
Installing collected packages: uvloop, typing-extensions, python-dotenv, psutil, paho-mqtt, idna, httptools, h11, click, annotated-types, uvicorn, typing-inspection, pydantic-core, anyio, starlette, pydantic, fastapi

Successfully installed annotated-types-0.7.0 anyio-4.13.0 click-8.3.1 fastapi-0.115.12 h11-0.16.0 httptools-0.6.4 idna-3.11 paho-mqtt-2.1.0 psutil-7.2.2 pydantic-2.12.5 pydantic-core-2.41.5 python-dotenv-1.2.2 starlette-0.46.2 typing-extensions-4.15.0 typing-inspection-0.4.2 uvicorn-0.34.2 uvloop-0.21.0

## Usage



## Config

Edit `config.py`:



## API Flow



Sessions are logged to `ctlr.db` (SQLite).
