# Local verification results

Run on: 2026-11-26 12:15 | Windows | Python 3.12.3 | Node v24.22.3

| Step | Result |
|---|---|
| Backend: install dev requirements | PASS |
| Backend: ruff lint | PASS |
| Backend: mypy type-check | PASS |
| Backend: unit tests | PASS |
| Backend: integration tests (API + SQLite; Postgres concurrency via Testcontainers/Docker) | PASS |
| Backend: Alembic migrations | PASS |
| Frontend: npm install | PASS |
| Frontend: TypeScript type-check | PASS |
| Frontend: lint | PASS |
| Frontend: production build | PASS |

### Backend: install dev requirements - PASS
```

```

### Backend: ruff lint - PASS
```
All checks passed!
```

### Backend: mypy type-check - PASS
```
Success: no issues found in 140 source files
```

### Backend: unit tests - PASS
```
........................................................................ [ 80%]
.................                                                        [100%]
89 passed in 3.19s
```

### Backend: integration tests (API + SQLite; Postgres concurrency via Testcontainers/Docker) - PASS
```
.....................                                                    [100%]
21 passed in 18.42s
```

### Backend: Alembic migrations - PASS
```
python.exe : INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
At C:\Users\suhas\Downloads\NextBot-AI-Complete-Project 
(1)\NextBot-AI\scripts\verify.ps1:42 char:107
+ ... lite+aiosqlite:///./verify.db"; & $py -m alembic upgrade head; Remove ...
+                                     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (INFO  [alembic....mpl SQLiteImpl.:String) [ 
   ], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, Initial schema: 33 
domain entities + KnowledgeChunk, OutboxEvent, ProcessedEvent; pgvector extension + HNSW 
index.
```

### Frontend: npm install - PASS
```
up to date in 2s
```

### Frontend: TypeScript type-check - PASS
```
> nextbot-frontend@1.0.0 typecheck
> tsc --noEmit
```

### Frontend: lint - PASS
```
> nextbot-frontend@1.0.0 lint
> next lint
node.exe : `next lint` is deprecated and will be removed in Next.js 16.
At line:1 char:1
+ & "C:\Program Files\nodejs/node.exe" "C:\Users\suhas\AppData\Roaming\ ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (`next lint` is ... in Next.js 16.:String) [ 
   ], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
For new projects, use create-next-app to choose your preferred linter.
For existing projects, migrate to the ESLint CLI:
npx @next/codemod@canary next-lint-to-eslint-cli .
Γ£ö No ESLint warnings or errors
```

### Frontend: production build - PASS
```
 Γ£ô Compiled successfully in 2.2s
   Linting and checking validity of types ...
   Collecting page data ...
   Generating static pages (0/22) ...
   Generating static pages (5/22) 
   Generating static pages (10/22) 
   Generating static pages (16/22) 
 Γ£ô Generating static pages (22/22)
   Finalizing page optimization ...
   Collecting build traces ...
Route (app)                                 Size  First Load JS
Γöî Γùï /                                    1.93 kB         108 kB
Γö£ Γùï /_not-found                            995 B         104 kB
Γö£ Γùï /addresses                           1.08 kB         113 kB
Γö£ Γùï /admin                               1.07 kB         112 kB
Γö£ Γùï /admin/agents                        4.93 kB         111 kB
Γö£ Γùï /admin/analytics                     1.07 kB         112 kB
Γö£ Γùï /admin/approvals                     4.87 kB         111 kB
Γö£ Γùï /admin/inventory                     4.81 kB         111 kB
Γö£ Γùï /admin/orders                        5.01 kB         111 kB
Γö£ Γùï /admin/plugins                       4.89 kB         111 kB
Γö£ ╞Æ /admin/plugins/[id]                  5.18 kB         111 kB
Γö£ Γùï /assistant                           2.62 kB         113 kB
Γö£ Γùï /cart                                4.99 kB         111 kB
Γö£ Γùï /checkout                            1.79 kB         113 kB
Γö£ Γùï /dashboard                           4.81 kB         111 kB
Γö£ Γùï /login                               3.83 kB         110 kB
Γö£ Γùï /orders                              4.41 kB         111 kB
Γö£ ╞Æ /orders/[id]                         5.14 kB         111 kB
Γö£ Γùï /products                            1.42 kB         112 kB
Γö£ ╞Æ /products/[id]                       5.14 kB         111 kB
Γö£ Γùï /register                            3.58 kB         110 kB
Γö£ Γùï /returns                             4.93 kB         111 kB
Γöö Γùï /support                             3.28 kB         114 kB
+ First Load JS shared by all             103 kB
  Γö£ chunks/255-73938ce8a8eac1ad.js       46.6 kB
  Γö£ chunks/4bd1b696-c023c6e3521b1417.js  54.2 kB
  Γöö other shared chunks (total)          1.99 kB
Γùï  (Static)   prerendered as static content
╞Æ  (Dynamic)  server-rendered on demand
```

