/*
 *  Licensed to the Apache Software Foundation (ASF) under one
 *  or more contributor license agreements.  See the NOTICE file
 *  distributed with this work for additional information
 *  regarding copyright ownership.  The ASF licenses this file
 *  to you under the Apache License, Version 2.0 (the
 *  "License"); you may not use this file except in compliance
 *  with the License.  You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing,
 *  software distributed under the License is distributed on an
 *  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 *  KIND, either express or implied.  See the License for the
 *  specific language governing permissions and limitations
 *  under the License.
 */

document.addEventListener("change", (event) => {
	const box = event.target;
	if (!box.matches("input[name='email_cc'], input[name='email_bcc']")) return;
	if (!box.checked) return;
	const name = box.name === "email_cc" ? "email_bcc" : "email_cc";
	const partner = box.closest("tr").querySelector(`input[name='${name}']`);
	(partner.disabled ? box : partner).checked = false;
});
