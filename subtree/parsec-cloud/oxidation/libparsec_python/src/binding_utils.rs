// Parsec Cloud (https://parsec.cloud) Copyright (c) BSLv1.1 (eventually AGPLv3) 2016-2021 Scille SAS

use fancy_regex::Regex;
use pyo3::basic::CompareOp;
use pyo3::conversion::IntoPy;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::PyModule;
use pyo3::types::{PyFrozenSet, PyTuple};
use pyo3::FromPyObject;
use pyo3::{PyAny, PyObject, PyResult, Python};
use std::collections::HashSet;
use std::hash::Hash;

pub fn comp_op<T: std::cmp::PartialOrd>(op: CompareOp, h1: T, h2: T) -> PyResult<bool> {
    Ok(match op {
        CompareOp::Eq => h1 == h2,
        CompareOp::Ne => h1 != h2,
        CompareOp::Lt => h1 < h2,
        CompareOp::Le => h1 <= h2,
        CompareOp::Gt => h1 > h2,
        CompareOp::Ge => h1 >= h2,
    })
}

pub fn hash_generic(value_to_hash: &str, py: Python) -> PyResult<isize> {
    let builtins = PyModule::import(py, "builtins")?;
    let hash = builtins
        .getattr("hash")?
        .call1((value_to_hash,))?
        .extract::<isize>()?;
    Ok(hash)
}

pub fn py_to_rs_datetime(timestamp: &PyAny) -> PyResult<parsec_api_types::DateTime> {
    let ts_any =
        Python::with_gil(|_py| -> PyResult<&PyAny> { timestamp.getattr("timestamp")?.call0() })?;
    let ts = ts_any.extract::<f64>()?;
    Ok(parsec_api_types::DateTime::from_f64_with_us_precision(ts))
}

pub fn rs_to_py_datetime(py: Python, datetime: parsec_api_types::DateTime) -> PyResult<&PyAny> {
    let pendulum = PyModule::import(py, "pendulum")?;
    let args = PyTuple::new(py, vec![datetime.get_f64_with_us_precision()]);
    pendulum.call_method1("from_timestamp", args)
}

pub fn rs_to_py_realm_role(role: &parsec_api_types::RealmRole) -> PyResult<PyObject> {
    Python::with_gil(|py| -> PyResult<PyObject> {
        let cls = py.import("parsec.api.protocol")?.getattr("RealmRole")?;
        let role_name = match role {
            parsec_api_types::RealmRole::Owner => "OWNER",
            parsec_api_types::RealmRole::Manager => "MANAGER",
            parsec_api_types::RealmRole::Contributor => "CONTRIBUTOR",
            parsec_api_types::RealmRole::Reader => "READER",
        };
        let obj = cls.getattr(role_name)?;
        Ok(obj.into_py(py))
    })
}

pub fn py_to_rs_realm_role(role: &PyAny) -> PyResult<Option<parsec_api_types::RealmRole>> {
    if role.is_none() {
        return Ok(None);
    }
    use parsec_api_types::RealmRole::*;
    Ok(Some(match role.getattr("name")?.extract::<&str>()? {
        "OWNER" => Owner,
        "MANAGER" => Manager,
        "CONTRIBUTOR" => Contributor,
        "READER" => Reader,
        _ => unreachable!(),
    }))
}

pub fn py_to_rs_user_profile(profile: &PyAny) -> PyResult<parsec_api_types::UserProfile> {
    use parsec_api_types::UserProfile::*;
    Ok(match profile.getattr("name")?.extract::<&str>()? {
        "ADMIN" => Admin,
        "STANDARD" => Standard,
        "OUTSIDER" => Outsider,
        _ => unreachable!(),
    })
}

pub fn py_to_rs_invitation_status(
    status: &PyAny,
) -> PyResult<parsec_api_protocol::InvitationStatus> {
    use parsec_api_protocol::InvitationStatus::*;
    Ok(match status.getattr("name")?.extract::<&str>()? {
        "IDLE" => Idle,
        "READY" => Ready,
        "DELETED" => Deleted,
        _ => unreachable!(),
    })
}

// This implementation is due to
// https://github.com/PyO3/pyo3/blob/39d2b9d96476e6cc85ca43e720e035e0cdff7a45/src/types/set.rs#L240
// where Hashset is PySet in FromPyObject trait
pub fn py_to_rs_set<'a, T: FromPyObject<'a> + Eq + Hash>(set: &'a PyAny) -> PyResult<HashSet<T>> {
    set.downcast::<PyFrozenSet>()?
        .iter()
        .map(T::extract)
        .collect::<PyResult<std::collections::HashSet<T>>>()
}

pub fn py_to_rs_regex(regex: &PyAny) -> PyResult<Regex> {
    let regex = regex
        .getattr("pattern")
        .unwrap_or(regex)
        .extract::<String>()?
        .replace("\\Z", "\\z")
        .replace("\\ ", "\x20");
    Regex::new(&regex).map_err(|e| PyValueError::new_err(e.to_string()))
}

macro_rules! parse_kwargs_optional {
    ($kwargs: ident $(,[$var: ident $(:$ty: ty)?, $name: literal $(,$function: ident)?])* $(,)?) => {
        $(let mut $var = None;)*
        if let Some($kwargs) = $kwargs {
            for arg in $kwargs {
                match arg.0.extract::<&str>()? {
                    $($name => $var = {
                        let temp = arg.1;
                        $(let temp = temp.extract::<$ty>()?;)?
                        $(let temp = $function(&temp)?;)?
                        Some(temp)
                    },)*
                    _ => unreachable!(),
                }
            }
        }
    };
}
macro_rules! parse_kwargs {
    ($kwargs: ident $(,[$var: ident $(:$ty: ty)?, $name: literal $(,$function: ident)?])* $(,)?) => {
        crate::binding_utils::parse_kwargs_optional!(
            $kwargs,
            $([$var $(:$ty)?, $name $(,$function)?],)*
        );
        $(let $var = $var.expect(concat!("Missing `", stringify!($name), "` argument"));)*
    };
}
pub(crate) use parse_kwargs;
pub(crate) use parse_kwargs_optional;
