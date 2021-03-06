# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2012 Managed I.T.
#
# Author: Kiall Mac Innes <kiall@managedit.ie>
# Modified: Patrick Galbraith <patg@hp.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import hashlib
from sqlalchemy import (Column, DateTime, String, Text, Integer, ForeignKey,
                        Enum, Boolean, Unicode, UniqueConstraint, event)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.hybrid import hybrid_property
from designate.openstack.common import log as logging
from designate.openstack.common import timeutils
from designate.openstack.common.uuidutils import generate_uuid
from designate.sqlalchemy.types import UUID
from designate.sqlalchemy.models import Base as CommonBase
from designate.sqlalchemy.models import SoftDeleteMixin
from sqlalchemy.ext.declarative import declarative_base

LOG = logging.getLogger(__name__)

RECORD_TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'SRV', 'TXT', 'SPF', 'NS', 'PTR',
                'SSHFP']
TSIG_ALGORITHMS = ['hmac-md5', 'hmac-sha1', 'hmac-sha224', 'hmac-sha256',
                   'hmac-sha384', 'hmac-sha512']


class Base(CommonBase):
    id = Column(UUID, default=generate_uuid, primary_key=True)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=timeutils.utcnow)
    updated_at = Column(DateTime, onupdate=timeutils.utcnow)

    __mapper_args__ = {
        'version_id_col': version
    }


Base = declarative_base(cls=Base)


class Quota(Base):
    __tablename__ = 'quotas'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'resource', name='unique_quota'),
    )

    tenant_id = Column(String(36), nullable=False)
    resource = Column(String(32), nullable=False)
    hard_limit = Column(Integer(), nullable=False)


class Server(Base):
    __tablename__ = 'servers'

    name = Column(String(255), nullable=False, unique=True)


class Domain(SoftDeleteMixin, Base):
    __tablename__ = 'domains'
    __table_args__ = (
        UniqueConstraint('name', 'deleted', name='unique_domain_name'),
    )

    tenant_id = Column(String(36), default=None, nullable=True)

    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    description = Column(Unicode(160), nullable=True)

    ttl = Column(Integer, default=3600, nullable=False)
    refresh = Column(Integer, default=3600, nullable=False)
    retry = Column(Integer, default=600, nullable=False)
    expire = Column(Integer, default=86400, nullable=False)
    minimum = Column(Integer, default=3600, nullable=False)
    serial = Column(Integer, default=timeutils.utcnow_ts, nullable=False)

    records = relationship('Record', backref=backref('domain', uselist=False),
                           lazy='dynamic', cascade="all, delete-orphan",
                           passive_deletes=True)

    parent_domain_id = Column(UUID, ForeignKey('domains.id'), default=None,
                              nullable=True)


class Record(Base):
    __tablename__ = 'records'

    domain_id = Column(UUID, ForeignKey('domains.id', ondelete='CASCADE'),
                       nullable=False)

    type = Column(Enum(name='record_types', *RECORD_TYPES), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Unicode(160), nullable=True)

    data = Column(Text, nullable=False)
    priority = Column(Integer, default=None, nullable=True)
    ttl = Column(Integer, default=None, nullable=True)

    hash = Column(String(32), nullable=False, unique=True)

    managed = Column(Boolean, default=False)
    managed_plugin_type = Column(Unicode(50), default=None, nullable=True)
    managed_plugin_name = Column(Unicode(50), default=None, nullable=True)
    managed_resource_type = Column(Unicode(50), default=None, nullable=True)
    managed_resource_id = Column(UUID, default=None, nullable=True)

    @hybrid_property
    def tenant_id(self):
        return self.domain.tenant_id

    def recalculate_hash(self):
        """
        Calculates the hash of the record, used to ensure record uniqueness.
        """
        md5 = hashlib.md5()
        md5.update("%s:%s:%s:%s:%s" % (self.domain_id, self.name, self.type,
                                       self.data, self.priority))

        self.hash = md5.hexdigest()

    def _extra_keys(self):
        return ['tenant_id']


@event.listens_for(Record, "before_insert")
def recalculate_record_hash_before_insert(mapper, connection, instance):
    instance.recalculate_hash()


@event.listens_for(Record, "before_update")
def recalculate_record_hash_before_update(mapper, connection, instance):
    instance.recalculate_hash()


class TsigKey(Base):
    __tablename__ = 'tsigkeys'

    name = Column(String(255), nullable=False, unique=True)
    algorithm = Column(Enum(name='tsig_algorithms', *TSIG_ALGORITHMS),
                       nullable=False)
    secret = Column(String(255), nullable=False)
