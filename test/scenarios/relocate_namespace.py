#!/usr/bin/env python
# Copyright 2010-2014 RethinkDB, all rights reserved.

import sys, os, time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, 'common')))
import http_admin, driver, workload_runner, scenario_common, rdb_workload_common
from vcoptparse import *

op = OptParser()
scenario_common.prepare_option_parser_mode_flags(op)
workload_runner.prepare_option_parser_for_split_or_continuous_workload(op)
op["num-nodes"] = IntFlag("--num-nodes", 2)
opts = op.parse(sys.argv)

with driver.Metacluster() as metacluster:
    cluster = driver.Cluster(metacluster)
    executable_path, command_prefix, serve_options = scenario_common.parse_mode_flags(opts)
    print "Starting cluster..."
    processes = [driver.Process(
    		cluster,
			driver.Files(metacluster, db_path="db-%d" % i, console_output="create-output-%d" % i, command_prefix=command_prefix),
			console_output="serve-output-%d" % i, command_prefix=command_prefix, extra_options=serve_options)
		 for i in xrange(opts["num-nodes"])]
    for process in processes:
        process.wait_until_started_up()

    print "Creating table..."
    http = http_admin.ClusterAccess([("localhost", p.http_port) for p in processes])
    primary_dc = http.add_datacenter()
    secondary_dc = http.add_datacenter()
    servers = http.servers.keys()
    http.move_server_to_datacenter(servers[0], primary_dc)
    http.move_server_to_datacenter(servers[1], secondary_dc)
    ns = scenario_common.prepare_table_for_workload(http, primary = primary_dc)
    http.wait_until_blueprint_satisfied(ns)
    cluster.check()
    http.check_no_issues()

    workload_ports = scenario_common.get_workload_ports(ns, processes)
    with workload_runner.SplitOrContinuousWorkload(opts, workload_ports) as workload:
        workload.run_before()
        cluster.check()
        http.check_no_issues()
        http.move_table_to_datacenter(ns, secondary_dc)
        http.wait_until_blueprint_satisfied(ns)
        rdb_workload_common.wait_for_table(
            host=workload_ports.host,
            port=workload_ports.rdb_port,
            table=workload_ports.table_name
        )
        cluster.check()
        http.check_no_issues()
        workload.run_after()

    cluster.check_and_stop()
