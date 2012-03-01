#!/usr/bin/env python
"""
SQLAlchemy wrapping of motor database

Main Class for full Database:  MotorDB

"""
import os
import json
import epics
import time
import socket

from datetime import datetime

from utils import backup_versions, save_backup

from sqlalchemy import MetaData, create_engine, and_, \
     Table, Column, Integer, Float, String, Text, DateTime, ForeignKey

from sqlalchemy.orm import sessionmaker,  mapper, clear_mappers, relationship
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import  NoResultFound
from sqlalchemy.pool import SingletonThreadPool

# needed for py2exe?
import sqlalchemy.dialects.sqlite

def isMotorDB(dbname):
    """test if a file is a valid motor Library file:
       must be a sqlite db file, with tables named 'motor'
    """
    result = False
    try:
        engine = create_engine('sqlite:///%s' % dbname,
                               poolclass=SingletonThreadPool)
        meta = MetaData(engine)
        meta.reflect()
        if ('info' in meta.tables and 'motors' in meta.tables):
            keys = [row.key for row in
                    meta.tables['info'].select().execute().fetchall()]
            result = 'version' in keys and 'create_date' in keys
    except:
        pass
    return result

def json_encode(val):
    "simple wrapper around json.dumps"
    if val is None or isinstance(val, (str, unicode)):
        return val
    return  json.dumps(val)

def valid_score(score, smin=0, smax=5):
    """ensure that the input score is an integr
    in the range [smin, smax]  (inclusive)"""
    return max(smin, min(smax, int(score)))


def isotime2datetime(isotime):
    "convert isotime string to datetime object"
    sdate, stime = isotime.replace('T', ' ').split(' ')
    syear, smon, sday = [int(x) for x in sdate.split('-')]
    sfrac = '0'
    if '.' in stime:
        stime, sfrac = stime.split('.')
    shour, smin, ssec  = [int(x) for x in stime.split(':')]
    susec = int(1e6*float('.%s' % sfrac))

    return datetime(syear, smon, sday, shour, smin, ssec, susec)

def None_or_one(val, msg='Expected 1 or None result'):
    """expect result (as from query.all() to return
    either None or exactly one result
    """
    if len(val) == 1:
        return val[0]
    elif len(val) == 0:
        return None
    else:
        raise MotorDBException(msg)


class MotorDBException(Exception):
    """DB Access Exception: General Errors"""
    def __init__(self, msg):
        Exception.__init__(self)
        self.msg = msg
    def __str__(self):
        return self.msg


def StrCol(name, size=None, **kws):
    if size is None:
        return Column(name, Text, **kws)
    else:
        return Column(name, String(size), **kws)

def NamedTable(tablename, metadata, keyid='id', nameid='name',
               name=True, notes=True, attributes=True, cols=None):
    args  = [Column(keyid, Integer, primary_key=True)]
    if name:
        args.append(StrCol(nameid, nullable=False, unique=True))
    if notes:
        args.append(StrCol('notes'))
    if attributes:
        args.append(StrCol('attributes'))
    if cols is not None:
        args.extend(cols)
    return Table(tablename, metadata, *args)

def make_newdb(dbname, server= 'sqlite'):
    engine  = create_engine('%s:///%s' % (server, dbname))
    metadata =  MetaData(engine)
    
    x = NamedTable('motors', metadata,
                   cols=[StrCol('dtype'),
                         StrCol('description'), 
                         StrCol('units'), 
                         Column('card', Integer), 
                         Column('dir',  Integer), 
                         Column('velo', Float),
                         Column('vbas', Float),
                         Column('accl', Float),
                         Column('bdst', Float),
                         Column('bvel', Float),
                         Column('bacc', Float),
                         Column('srev', Float),
                         Column('urev', Float),
                         Column('prec', Float),
                         Column('dhlm', Float),
                         Column('dllm', Float) ])

    info = Table('info', metadata,
                 Column('key', Text, primary_key=True, unique=True), 
                 StrCol('value'))

    metadata.create_all()
    session = sessionmaker(bind=engine)()
    now = datetime.isoformat(datetime.now())
    for key, value in (["version", "0.1"],
                       ["verify_erase", "1"],
                       ["verify_overwrite",  "1"],
                       ["create_date", '<now>'],
                       ["modify_date", '<now>']):
        if value == '<now>':
            value = now
        info.insert().execute(key=key, value=value)

    session.commit()    

class _BaseTable(object):
    "generic class to encapsulate SQLAlchemy table"
    def __repr__(self):
        name = self.__class__.__name__
        fields = ['%s' % getattr(self, 'name', 'UNNAMED')]
        return "<%s(%s)>" % (name, ', '.join(fields))

class InfoTable(_BaseTable):
    "general information table (versions, etc)"
    key, value = None, None
    def __repr__(self):
        name = self.__class__.__name__
        fields = ['%s=%s' % (getattr(self, 'key', '?'),
                             getattr(self, 'value', '?'))]
        return "<%s(%s)>" % (name, ', '.join(fields))

class MotorsTable(_BaseTable):
    "motors table"
    name, notes = None, None

class MotorDB(object):
    "interface to Motors Database"
    def __init__(self, dbname=None):
        self.dbname = dbname
        self.tables = None
        self.engine = None
        self.session = None
        self.conn    = None
        self.metadata = None
        self.pvs = {}
        self.restoring_pvs = []
        if dbname is not None:
            self.connect(dbname)

    def create_newdb(self, dbname, connect=False):
        "create a new, empty database"
        # backup_versions(dbname)
        make_newdb(dbname)
        if connect:
            time.sleep(0.5)
            self.connect(dbname, backup=False)

    def connect(self, dbname, backup=True):
        "connect to an existing database"
        if not os.path.exists(dbname):
            raise IOError("Database '%s' not found!" % dbname)

        if not isMotorDB(dbname):
            raise ValueError("'%s' is not an Motor file!" % dbname)

        if backup:
            save_backup(dbname)
        self.dbname = dbname
        self.engine = create_engine('sqlite:///%s' % self.dbname,
                                    poolclass = SingletonThreadPool)
        self.conn = self.engine.connect()
        self.session = sessionmaker(bind=self.engine)()

        self.metadata =  MetaData(self.engine)
        self.metadata.reflect()
        tables = self.tables = self.metadata.tables

        try:
            clear_mappers()
        except:
            pass

        mapper(MotorsTable,   tables['motors'])
        mapper(InfoTable,   tables['info'])

    def commit(self):
        "commit session state"
        self.set_info('modify_date', datetime.isoformat(datetime.now()))
        return self.session.commit()

    def close(self):
        "close session"
        self.set_hostpid(clear=True)
        self.session.commit()
        self.session.flush()
        self.session.close()

    def query(self, *args, **kws):
        "generic query"
        return self.session.query(*args, **kws)

    def get_info(self, key, default=None):
        """get a value from a key in the info table"""
        errmsg = "get_info expected 1 or None value for key='%s'"
        out = self.query(InfoTable).filter(InfoTable.key==key).all()
        thisrow = None_or_one(out, errmsg % key)
        if thisrow is None:
            return default
        return thisrow.value

    def set_info(self, key, value):
        """set key / value in the info table"""
        table = self.tables['info']
        vals  = self.query(table).filter(InfoTable.key==key).all()
        if len(vals) < 1:
            table.insert().execute(key=key, value=value)
        else:
            table.update(whereclause="key='%s'" % key).execute(value=value)

    def set_hostpid(self, clear=False):
        """set hostname and process ID, as on intial set up"""
        name, pid = '', '0'
        if not clear:
            name, pid = socket.gethostname(), str(os.getpid())
        self.set_info('host_name', name)
        self.set_info('process_id', pid)

    def check_hostpid(self):
        """check whether hostname and process ID match current config"""
        db_host_name = self.get_info('host_name', default='')
        db_process_id  = self.get_info('process_id', default='0')
        return ((db_host_name == '' and db_process_id == '0') or
                (db_host_name == socket.gethostname() and
                 db_process_id == str(os.getpid())))

    def __addRow(self, table, argnames, argvals, **kws):
        """add generic row"""
        me = table() #
        for name, val in zip(argnames, argvals):
            setattr(me, name, val)
        for key, val in kws.items():
            if key == 'attributes':
                val = json_encode(val)
            setattr(me, key, val)
        try:
            self.session.add(me)
            # self.session.commit()
        except IntegrityError, msg:
            self.session.rollback()
            raise Warning('Could not add data to table %s\n%s' % (table, msg))

        return me


    def _get_foreign_keyid(self, table, value, name='name',
                           keyid='id', default=None):
        """generalized lookup for foreign key
arguments
    table: a valid table class, as mapped by mapper.
    value: can be one of the following
         table instance:  keyid is returned
         string:          'name' attribute (or set which attribute with 'name' arg)
            a valid id
            """
        if isinstance(value, table):
            return getattr(table, keyid)
        else:
            if isinstance(value, (str, unicode)):
                xfilter = getattr(table, name)
            elif isinstance(value, int):
                xfilter = getattr(table, keyid)
            else:
                return default
            try:
                query = self.query(table).filter(
                    xfilter==value)
                return getattr(query.one(), keyid)
            except (IntegrityError, NoResultFound):
                return default

        return default

    def get_all_motors(self):
        """return motor list list
        """
        return [m for m in self.query(MotorsTable)]

    def get_motor(self, name):
        """return motor by name
        """
        if isinstance(name, MotorsTable):
            return name
        out = self.query(MotorsTable).filter(MotorsTable.name==name).all()
        return None_or_one(out, 'get_motor expected 1 or None Motor')

    def add_motor(self, name, notes=None,
                  attributes=None, **kws):
        """add instrument
        notes and attributes optional
        returns Instruments instance"""
        kws['notes'] = notes
        kws['attributes'] = attributes
        name = name.strip()
        row = self.__addRow(MotorsTable, ('name',), (name,), **kws)
        self.session.add(row)
        self.commit()
        return row

    def add_info(self, key, value):
        """add Info key value pair -- returns Info instance"""
        row = self.__addRow(InfoTable, ('key', 'value'), (key, value))
        self.commit()
        return row

    def remove_motor(self, motor):
        m = self.get_motor(motor)
        if m is None:
            raise MotorDBException('Remove Motor needs valid motor')

        tab = self.tables['motors']
        self.conn.execute(tab.delete().where(tab.c.id==inst.id))

