To run supervisor example
--------------------------

run two supervisors, and kill the first one

supervisord -n -c example/supervisor.ini

supervisord -n -c example/supervisor-2nd.ini


Quick test supervisor
--------------------------

To quickly test/try single-beat 

```
single-beat python echo.py
```