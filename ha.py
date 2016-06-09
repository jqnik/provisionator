#!/usr/bin/env python

#
# (c) Copyright 2015 Cloudera, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import logging
import sys
import time

from cm_api.api_client import ApiException

import cluster
import config
import mgmt
import util
from errors import ProvisionatorException

LOG = logging.getLogger(__name__)
logging.basicConfig()
LOG.setLevel(logging.INFO)

def enable_hdfsha(conf):
    ha_hosts_map = {}
    active_namenode_key = "ActiveNamenode"
    standby_namenode_key = "StandbyNamenode"
    journalnode1_key = "JournalNode1"
    journalnode2_key = "JournalNode2"
    journalnode3_key = "JournalNode3"

    try:
        # Open a connection to CM and get a CM object
        api = util.get_api_handle(conf)
        cm = api.get_cloudera_manager()
        cl = None
        if 'cluster' in conf and 'name' in conf['cluster']:
            cl = api.get_cluster(conf['cluster']['name'])
        else:
            raise ProvisionatorException("No cluster specified")

        #todo: check if enabled already
        hdfs_svc = config.get_cluster_service_by_type(conf, 'HDFS')
        hdfs = cl.get_service(hdfs_svc['name'])
        hdfs_cfg, hdfs_roletype_cfg = hdfs.get_config(view='full')
        host_id_map = util.host_id_map(config, api)
        active_namenode = hdfs_svc['haconfig']['active_namenode']
        standby_namenode = hdfs_svc['haconfig']['standby_namenode']
        journalnode1 = hdfs_svc['haconfig']['journalnode1']
        journalnode2 = hdfs_svc['haconfig']['journalnode2']
        journalnode3 = hdfs_svc['haconfig']['journalnode3']
        ns = hdfs_svc['haconfig']['ns']
        jnEditsDir = hdfs_svc['haconfig']['jnEditsDir']

        ha_hosts_map[active_namenode_key] = active_namenode
        ha_hosts_map[standby_namenode_key] = standby_namenode
        ha_hosts_map[journalnode1_key] = journalnode1
        ha_hosts_map[journalnode2_key] = journalnode2
        ha_hosts_map[journalnode3_key] = journalnode3

        LOG.info("host_id_map: " + str(host_id_map))
        LOG.info("ha_host_map: " + str(ha_hosts_map))
    	for ha_host in ha_hosts_map:
		LOG.info ("ha_hosts_map[ha_host]: " + ha_hosts_map[ha_host])
		try:
			LOG.info("Host ID for " + ha_host + ": "+ host_id_map[ha_hosts_map[ha_host]])
		except KeyError:
			LOG.error("Cannot find host " + ha_hosts_map[ha_host] + " for role \""
				+ ha_host + "\" in list of hosts (" + str(list(host_id_map)) + ")")
			return


        jns = []
        jns.append({'jnHostId': host_id_map[journalnode1], 'jnName': journalnode1_key, 'jnEditsDir': jnEditsDir})
        jns.append({'jnHostId': host_id_map[journalnode2], 'jnName': journalnode2_key, 'jnEditsDir': jnEditsDir})
        jns.append({'jnHostId': host_id_map[journalnode3], 'jnName': journalnode3_key, 'jnEditsDir': jnEditsDir})

        zk_svc = config.get_cluster_service_by_type(conf, 'ZOOKEEPER')
        zk_svc_name = zk_svc['name']

        nn = hdfs.get_roles_by_type("NAMENODE")

        if not nn:
            raise ProvisionatorException("Could not find the active Namenode for current configuration")



        if len([instance.name for instance in nn]) > 1:
            LOG.warn("Found more than one Namnode in current configuration")
        nn_name = ([instance.name for instance in nn])[0]
        LOG.info("Active Namenode name in current config: " + nn_name)

        LOG.info("Running HDFS HA configuration now...")
        # standby_host_id - ID of host where Standby NameNode will be created.
        # nameservice - Nameservice to be used while enabling HA
        # jns - List of Journal Nodes. Each element must be a dict containing the following keys:
        # jnHostId: ID of the host where the new JournalNode will be created.
        # jnName: Name of the JournalNode role (optional)
        # jnEditsDir: Edits dir of the JournalNode. Can be omitted if the config is already set at RCG level.
        # zk_service_name - Name of the ZooKeeper service to use for auto-failover.
        cmd = hdfs.enable_nn_ha(
            nn_name,
            host_id_map[standby_namenode],
            ns,
            jns,
            standby_name_dir_list=None,
            qj_name=None,
            standby_name=None,
            active_fc_name=None,
            standby_fc_name=None,
            zk_service_name=zk_svc_name,
            force_init_znode=True,
            clear_existing_standby_name_dirs=True,
            clear_existing_jn_edits_dir=True
        )

        util.wait_for_command(cmd, True)
        #TODO: in some cases time.sleep(x) is needed to avoid race conditions
        try:
	    mgmt_svc = cm.get_service()
	    LOG.info("Restarting management services")
	    mgmt.restart(cm)
        except ApiException:
	    pass
        LOG.info("Restarting cluster")
        cluster.restart(cl)
    except ApiException, e:
        raise ProvisionatorException(e)

def enable_rmha(conf):

    ha_hosts_map = {}
    standby_rm_key = "StandbyResourceManager"

    try:
        # Open a connection to CM and get a CM object
        api = util.get_api_handle(conf)
        cm = api.get_cloudera_manager()
        cl = None
        if 'cluster' in conf and 'name' in conf['cluster']:
            cl = api.get_cluster(conf['cluster']['name'])
        else:
            raise ProvisionatorException("No cluster specified")


        host_id_map = util.host_id_map(config, api)

        #todo: check if enabled already
        yarn_svc = config.get_cluster_service_by_type(conf, 'YARN')
        yarn = cl.get_service(yarn_svc['name'])
        standby_rm = yarn_svc['haconfig']['standby_rm']
        ha_hosts_map[standby_rm_key] = standby_rm

        LOG.info("host_id_map: " + str(host_id_map))
        LOG.info("ha_host_map: " + str(ha_hosts_map))
            for ha_host in ha_hosts_map:
            LOG.info ("ha_hosts_map[ha_host]: " + ha_hosts_map[ha_host])
            try:
                LOG.info("Host ID for " + ha_host + ": "+ host_id_map[ha_hosts_map[ha_host]])
            except KeyError:
                LOG.error("Cannot find host " + ha_hosts_map[ha_host] + " for role \""
                    + ha_host + "\" in list of hosts (" + str(list(host_id_map)) + ")")
                return

        zk_svc = config.get_cluster_service_by_type(conf, 'ZOOKEEPER')
        zk_svc_name = zk_svc['name']

        LOG.info("Running YARN HA configuration now...")
        # new_rm_host_id - ID of host where Standby Resource Manager will be created.
        # zk_service_name - Name of the ZooKeeper service to use for auto-failover.
        cmd = yarn.enable_rm_ha(
            host_id_map[standby_rm],
            zk_service_name=zk_svc_name
        )

        util.wait_for_command(cmd, True)
        #TODO: in some cases time.sleep(x) is needed to avoid race conditions
        try:
            mgmt_svc = cm.get_service()
            LOG.info("Restarting management services")
            mgmt.restart(cm)
        except ApiException:
	        pass

        LOG.info("Restarting cluster")
        cluster.restart(cl)
    except ApiException, e:
        raise ProvisionatorException(e)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logging.fatal("No configuration file specified")
        sys.exit(-1)

    conf = config.read_config(sys.argv[1])

    enable_hdfsha(conf)
    enable_rmha(conf)
